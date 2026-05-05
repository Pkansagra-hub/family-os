"""Unit tests for ``SQLiteProjectionStore`` + ``SQLiteSessionStore`` (M3.E4.I1)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from k1.selfmodel.adapters.sqlite_migrations import current_user_version
from k1.selfmodel.adapters.sqlite_projection_store import (
    SQLiteProjectionStore,
    SQLiteSessionStore,
    default_db_path,
)
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConflictDescriptor,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.family_model import (
    FamilyMemberRef,
    FamilySelfModelSnapshot,
    RelationshipEdge,
    RoutineRef,
)
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.ports.identity import IdentitySession, IdentityTier
from k1.selfmodel.ports.projection_store import ProjectionFreshness

T_MS = 1_700_000_000_000
WRITER = "selfmodel:test"


def _store(tmp_path: Path, *, allowed=(WRITER,)) -> SQLiteProjectionStore:
    return SQLiteProjectionStore(tmp_path / "s.db", allowed_writers=allowed)


# ---------------------------------------------------------------------
# Construction + PRAGMAs + migrations
# ---------------------------------------------------------------------
def test_construction_applies_migrations(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        assert current_user_version(s.connection) >= 1
    finally:
        s.close()


def test_construction_creates_parent_dirs(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "s.db"
    s = SQLiteProjectionStore(deep)
    s.close()
    assert deep.exists()


def test_default_db_path_is_under_homedir() -> None:
    p = default_db_path()
    assert p.suffix == ".db"
    assert ".familyos" in p.parts


def test_pragmas_set(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        jm = s.connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(jm).lower() == "wal"
        bt = s.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        assert int(bt) == 5000
        sync = s.connection.execute("PRAGMA synchronous").fetchone()[0]
        assert int(sync) == 1  # NORMAL
        fk = s.connection.execute("PRAGMA foreign_keys").fetchone()[0]
        assert int(fk) == 1
    finally:
        s.close()


def test_context_manager_closes(tmp_path: Path) -> None:
    p = tmp_path / "s.db"
    with SQLiteProjectionStore(p) as s:
        assert s is not None
    # Connection should be closed; another open should succeed.
    s2 = SQLiteProjectionStore(p)
    s2.close()


# ---------------------------------------------------------------------
# Self
# ---------------------------------------------------------------------
def _self(actor_id: str = "a1", *, l4_leak: bool = True) -> K1SelfModelSnapshot:
    return K1SelfModelSnapshot(
        actor_id=actor_id,
        revision="r1",
        L1_core={"name": "X"},
        L2_identity={"role": "guardian"},
        L3_pattern={"morning": True},
        L4_context={"leak": "do not persist"} if l4_leak else {},
        L5_state={"transient": True} if l4_leak else {},
        composed_at_ms=T_MS,
    )


def test_self_round_trip_strips_L4_L5(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        wr = s.write_self(_self(), writer_id=WRITER)
        assert wr.accepted
        snap, rd = s.read_self("a1")
        assert rd.found
        assert snap.L4_context == {}
        assert snap.L5_state == {}
        assert snap.L1_core == {"name": "X"}
        assert rd.revision.revision == wr.revision.revision
    finally:
        s.close()


def test_self_read_missing_returns_none(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        snap, rd = s.read_self("ghost")
        assert snap is None and rd.found is False
    finally:
        s.close()


def test_self_overwrite_chains_revisions(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        a = s.write_self(_self(), writer_id=WRITER)
        b = s.write_self(_self(), writer_id=WRITER)
        assert b.revision.parent_revision == a.revision.revision
    finally:
        s.close()


def test_self_writer_id_allowlist(tmp_path: Path) -> None:
    s = _store(tmp_path, allowed=(WRITER,))
    try:
        wr = s.write_self(_self(), writer_id="someone-else")
        assert wr.accepted is False
        assert "writer_id_not_allowed" in wr.reason
    finally:
        s.close()


def test_self_persists_across_reopen(tmp_path: Path) -> None:
    p = tmp_path / "s.db"
    s1 = SQLiteProjectionStore(p, allowed_writers=(WRITER,))
    s1.write_self(_self(), writer_id=WRITER)
    s1.close()
    s2 = SQLiteProjectionStore(p, allowed_writers=(WRITER,))
    try:
        snap, rd = s2.read_self("a1")
        assert rd.found and snap.L1_core == {"name": "X"}
    finally:
        s2.close()


# ---------------------------------------------------------------------
# Family
# ---------------------------------------------------------------------
def _family() -> FamilySelfModelSnapshot:
    return FamilySelfModelSnapshot(
        family_space_id="fs:home",
        revision="r1",
        members=(
            FamilyMemberRef(
                member_id="m1", display_name="Aanya", role="guardian", age_band="adult"
            ),
        ),
        relations=(
            RelationshipEdge(from_member="m1", to_member="m2", kind="parent_of", weight=2.0),
        ),
        routines=(RoutineRef(routine_id="rt1", name="bedtime", schedule="20:00"),),
        composed_at_ms=T_MS,
    )


def test_family_round_trip(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.write_family(_family(), writer_id=WRITER)
        snap, rd = s.read_family("fs:home")
        assert rd.found
        assert snap.members[0].display_name == "Aanya"
        assert snap.relations[0].weight == 2.0
        assert snap.routines[0].name == "bedtime"
    finally:
        s.close()


def test_family_writer_denial(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        wr = s.write_family(_family(), writer_id="ghost")
        assert wr.accepted is False
    finally:
        s.close()


# ---------------------------------------------------------------------
# Constitution
# ---------------------------------------------------------------------
def _constitution(version: str = "v0", parent: str = "") -> ConstitutionSnapshot:
    return ConstitutionSnapshot(
        constitution_id="c:home",
        version=version,
        parent_version=parent,
        body={"rules": {"a": 1}},
        signatures=(
            SigningProof(
                signer_id="g1", key_id="x", signature_b64="ZGVhZGJlZWY=", signed_at_ms=T_MS
            ),
        ),
        activated_at_ms=T_MS,
    )


def test_constitution_round_trip(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.write_constitution(_constitution(), writer_id=WRITER)
        snap, rd = s.read_constitution("c:home")
        assert rd.found
        assert snap.version == "v0"
        assert snap.body == {"rules": {"a": 1}}
        assert snap.signatures[0].signer_id == "g1"
    finally:
        s.close()


def test_constitution_history_appends(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.write_constitution(_constitution(version="v0"), writer_id=WRITER)
        s.write_constitution(_constitution(version="v1", parent="v0"), writer_id=WRITER)
        rows = s.connection.execute(
            "SELECT version FROM constitution_history WHERE constitution_id='c:home' ORDER BY version"
        ).fetchall()
        assert tuple(r["version"] for r in rows) == ("v0", "v1")
    finally:
        s.close()


def test_constitution_writer_denial(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        wr = s.write_constitution(_constitution(), writer_id="ghost")
        assert wr.accepted is False
    finally:
        s.close()


# ---------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------
def _amendment(
    amendment_id: str = "amd:1", *, parent: str = "v0", status=AmendmentStatus.DRAFT
) -> AmendmentProposal:
    return AmendmentProposal(
        amendment_id=amendment_id,
        parent_version=parent,
        proposed_by="g1",
        body={"rule": "x"},
        status=status,
        signatures=(),
        expires_at_ms=T_MS + 1000,
    )


def test_amendment_upsert_and_get(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.upsert_amendment(_amendment(), writer_id=WRITER)
        out = s.get_amendment("amd:1")
        assert out is not None
        assert out.proposed_by == "g1"
        assert out.body == {"rule": "x"}
        assert out.status == AmendmentStatus.DRAFT
    finally:
        s.close()


def test_amendment_upsert_updates_existing(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.upsert_amendment(_amendment(status=AmendmentStatus.DRAFT), writer_id=WRITER)
        s.upsert_amendment(_amendment(status=AmendmentStatus.PENDING), writer_id=WRITER)
        out = s.get_amendment("amd:1")
        assert out.status == AmendmentStatus.PENDING
    finally:
        s.close()


def test_amendment_get_missing(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        assert s.get_amendment("ghost") is None
    finally:
        s.close()


def test_amendment_with_conflict_round_trip(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        amd = AmendmentProposal(
            amendment_id="amd:c",
            parent_version="v0",
            proposed_by="g1",
            body={},
            status=AmendmentStatus.CONFLICT_PENDING,
            signatures=(),
            expires_at_ms=T_MS + 1,
            conflict=ConflictDescriptor(
                parent_version="v0",
                sibling_amendment_ids=("amd:s1", "amd:s2"),
                detected_at_ms=T_MS,
            ),
        )
        s.upsert_amendment(amd, writer_id=WRITER)
        out = s.get_amendment("amd:c")
        assert out.conflict is not None
        assert out.conflict.sibling_amendment_ids == ("amd:s1", "amd:s2")
    finally:
        s.close()


def test_amendment_sibling_parent_marks_conflict(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.write_constitution(_constitution(), writer_id=WRITER)
        s.upsert_amendment(
            _amendment("amd:1", parent="v0", status=AmendmentStatus.PENDING), writer_id=WRITER
        )
        wr = s.upsert_amendment(
            _amendment("amd:2", parent="v0", status=AmendmentStatus.PENDING), writer_id=WRITER
        )
        assert wr.reason == "conflict_pending"
        assert s.freshness("constitution:c:home") == ProjectionFreshness.CONFLICT_PENDING
    finally:
        s.close()


def test_amendment_writer_denial(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        wr = s.upsert_amendment(_amendment(), writer_id="ghost")
        assert wr.accepted is False
    finally:
        s.close()


# ---------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------
def test_append_signature_appends(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.upsert_amendment(_amendment(), writer_id=WRITER)
        proof = SigningProof(signer_id="g1", key_id="x", signature_b64="AAA=", signed_at_ms=T_MS)
        wr = s.append_signature("amd:1", proof, writer_id=WRITER)
        assert wr.accepted is True
        out = s.get_amendment("amd:1")
        assert len(out.signatures) == 1
        assert out.signatures[0].signer_id == "g1"
    finally:
        s.close()


def test_append_signature_unknown_amendment(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        proof = SigningProof(signer_id="g1", key_id="x", signature_b64="AAA=", signed_at_ms=T_MS)
        wr = s.append_signature("ghost", proof, writer_id=WRITER)
        assert wr.accepted is False
        assert wr.reason == "amendment_not_found"
    finally:
        s.close()


def test_append_signature_duplicate_signer_rejected(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.upsert_amendment(_amendment(), writer_id=WRITER)
        proof = SigningProof(signer_id="g1", key_id="x", signature_b64="AAA=", signed_at_ms=T_MS)
        s.append_signature("amd:1", proof, writer_id=WRITER)
        wr = s.append_signature("amd:1", proof, writer_id=WRITER)
        assert wr.accepted is False
        assert wr.reason == "duplicate_signer"
    finally:
        s.close()


def test_append_signature_writer_denial(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.upsert_amendment(_amendment(), writer_id=WRITER)
        proof = SigningProof(signer_id="g1", key_id="x", signature_b64="AAA=", signed_at_ms=T_MS)
        wr = s.append_signature("amd:1", proof, writer_id="ghost")
        assert wr.accepted is False
    finally:
        s.close()


# ---------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------
def test_freshness_default_fresh(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        assert s.freshness("self:a1") == ProjectionFreshness.FRESH
    finally:
        s.close()


def test_freshness_mark_and_clear(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.mark_stale("self:a1")
        assert s.freshness("self:a1") == ProjectionFreshness.STALE
        s.mark_offline_local_only("self:a1")
        assert s.freshness("self:a1") == ProjectionFreshness.OFFLINE_LOCAL_ONLY
        s.clear_freshness("self:a1")
        assert s.freshness("self:a1") == ProjectionFreshness.FRESH
    finally:
        s.close()


def test_write_self_clears_freshness_marker(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        s.mark_stale("self:a1")
        s.write_self(_self(), writer_id=WRITER)
        assert s.freshness("self:a1") == ProjectionFreshness.FRESH
    finally:
        s.close()


# ---------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------
def test_concurrent_writes_serialised(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        errors: list[Exception] = []

        def worker(actor_id: str) -> None:
            try:
                for _ in range(20):
                    s.write_self(_self(actor_id=actor_id), writer_id=WRITER)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"a{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        # All four actors readable.
        for i in range(4):
            snap, rd = s.read_self(f"a{i}")
            assert rd.found and snap is not None
    finally:
        s.close()


# ---------------------------------------------------------------------
# SQLiteSessionStore
# ---------------------------------------------------------------------
def test_session_store_round_trip(tmp_path: Path) -> None:
    s = _store(tmp_path)
    sess_store = SQLiteSessionStore(s)
    try:
        sess = IdentitySession(
            session_token="tok1",
            profile_id="p1",
            tier=IdentityTier.SOFT_CLAIM,
            device_id="dev:1",
            issued_at_ms=T_MS,
            hard_expires_at_ms=T_MS + 60_000,
        )
        sess_store.put(sess)
        got = sess_store.get("tok1")
        assert got is not None
        assert got.tier == IdentityTier.SOFT_CLAIM
        assert got.device_id == "dev:1"
    finally:
        s.close()


def test_session_store_get_missing(tmp_path: Path) -> None:
    s = _store(tmp_path)
    try:
        assert SQLiteSessionStore(s).get("ghost") is None
    finally:
        s.close()


def test_session_store_delete(tmp_path: Path) -> None:
    s = _store(tmp_path)
    sess_store = SQLiteSessionStore(s)
    try:
        sess_store.put(
            IdentitySession(
                session_token="t",
                profile_id="p",
                tier=IdentityTier.PIN_VERIFIED,
                device_id="d",
                issued_at_ms=T_MS,
                hard_expires_at_ms=T_MS + 1000,
            )
        )
        sess_store.delete("t")
        assert sess_store.get("t") is None
        sess_store.delete("ghost")  # no-op
    finally:
        s.close()


def test_session_store_purge_expired(tmp_path: Path) -> None:
    s = _store(tmp_path)
    sess_store = SQLiteSessionStore(s)
    try:
        for i in range(3):
            sess_store.put(
                IdentitySession(
                    session_token=f"t{i}",
                    profile_id=f"p{i}",
                    tier=IdentityTier.SOFT_CLAIM,
                    device_id="d",
                    issued_at_ms=T_MS,
                    hard_expires_at_ms=T_MS + 1000,
                )
            )
        # All within expiry: nothing purged.
        assert sess_store.purge_expired(now_ms=T_MS + 500) == 0
        # Past expiry: all 3 purged.
        n = sess_store.purge_expired(now_ms=T_MS + 5000)
        assert n == 3
        for i in range(3):
            assert sess_store.get(f"t{i}") is None
    finally:
        s.close()


def test_session_store_upsert_promotes_tier(tmp_path: Path) -> None:
    s = _store(tmp_path)
    sess_store = SQLiteSessionStore(s)
    try:
        sess_store.put(
            IdentitySession(
                session_token="t",
                profile_id="p",
                tier=IdentityTier.SOFT_CLAIM,
                device_id="d",
                issued_at_ms=T_MS,
                hard_expires_at_ms=T_MS + 1000,
            )
        )
        sess_store.put(
            IdentitySession(
                session_token="t",
                profile_id="p",
                tier=IdentityTier.STRONG_CRED,
                device_id="d",
                issued_at_ms=T_MS,
                hard_expires_at_ms=T_MS + 5000,
            )
        )
        out = sess_store.get("t")
        assert out.tier == IdentityTier.STRONG_CRED
        assert out.hard_expires_at_ms == T_MS + 5000
    finally:
        s.close()
