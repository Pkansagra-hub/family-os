"""``SQLiteProjectionStore`` — production projection store for k1.selfmodel.

Issue M3.E4.I1.

Implements every method on :class:`IProjectionStorePort` against a local
SQLite database (default path ``~/.familyos/k1/selfmodel.db``). Schema
is owned by ``k1.selfmodel.migrations`` and applied on first connect via
:func:`k1.selfmodel.adapters.sqlite_migrations.apply_migrations`.

PRAGMAs used (matches the SERVICE_DESIGN spec §5.4):

* ``journal_mode = WAL``
* ``synchronous = NORMAL``
* ``busy_timeout = 5000``
* ``foreign_keys = ON``

Thread safety: a single ``threading.RLock`` serialises all writes; reads
acquire the same lock for consistency. ``check_same_thread=False`` lets
multiple worker threads share the connection (the lock makes that safe
in CPython).

Identity sessions live alongside projections (M3 only needs the table;
the ``IdentitySessionManager`` reads/writes via a thin
:class:`SQLiteSessionStore` adapter exposed below).

L4_context / L5_state on ``K1SelfModelSnapshot`` MUST NOT be persisted —
mirrors the in-memory store's behaviour.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from k1.selfmodel.adapters.sqlite_migrations import apply_migrations
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConflictDescriptor,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.family_model import FamilySelfModelSnapshot
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.ports.identity import IdentitySession, IdentityTier
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
    ProjectionRevision,
    StoreReadResult,
    StoreWriteResult,
)
from k1.selfmodel.service.identity_session import IIdentitySessionStore

__all__ = [
    "SQLiteProjectionStore",
    "SQLiteSessionStore",
    "default_db_path",
]

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_revision_id() -> str:
    return uuid.uuid4().hex


def default_db_path() -> Path:
    """Return the default production DB path (``~/.familyos/k1/selfmodel.db``)."""
    return Path.home() / ".familyos" / "k1" / "selfmodel.db"


# ---------------------------------------------------------------------
# Projection store
# ---------------------------------------------------------------------
class SQLiteProjectionStore(IProjectionStorePort):
    """SQLite-backed implementation of ``IProjectionStorePort``."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        allowed_writers: tuple[str, ...] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._allowed_writers = (
            frozenset(allowed_writers) if allowed_writers is not None else None
        )
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,  # autocommit; we manage transactions
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_pragmas()
        apply_migrations(self._conn)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                logger.debug("wal_checkpoint failed at close", exc_info=True)
            self._conn.close()

    def __enter__(self) -> "SQLiteProjectionStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _configure_pragmas(self) -> None:
        c = self._conn
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA synchronous = NORMAL")
        c.execute("PRAGMA busy_timeout = 5000")
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA temp_store = MEMORY")

    def _check_writer(self, writer_id: str) -> StoreWriteResult | None:
        if self._allowed_writers is None:
            return None
        if writer_id not in self._allowed_writers:
            return StoreWriteResult(
                revision=ProjectionRevision(),
                accepted=False,
                reason=f"writer_id_not_allowed:{writer_id}",
            )
        return None

    # ------------------------------------------------------------------
    # Self
    # ------------------------------------------------------------------
    def read_self(
        self, actor_id: str
    ) -> tuple[K1SelfModelSnapshot | None, StoreReadResult]:
        with self._lock:
            row = self._conn.execute(
                "SELECT revision, parent_revision, written_at_ms, snapshot_json "
                "FROM self_projection WHERE actor_id = ?",
                (actor_id,),
            ).fetchone()
            freshness = self._read_freshness(f"self:{actor_id}")
        if row is None:
            return None, StoreReadResult(found=False, freshness=freshness)
        body = json.loads(row["snapshot_json"])
        snapshot = _self_from_json(body)
        revision = ProjectionRevision(
            revision=row["revision"],
            parent_revision=row["parent_revision"] or "",
            written_at_ms=int(row["written_at_ms"]),
        )
        return snapshot, StoreReadResult(found=True, revision=revision, freshness=freshness)

    def write_self(
        self, snapshot: K1SelfModelSnapshot, *, writer_id: str
    ) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        # Strip RAM-only layers BEFORE serialisation.
        cleaned = dataclasses.replace(snapshot, L4_context={}, L5_state={})
        body = _self_to_json(cleaned)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT revision FROM self_projection WHERE actor_id = ?",
                (snapshot.actor_id,),
            ).fetchone()
            parent = row["revision"] if row is not None else ""
            revision = ProjectionRevision(
                revision=_new_revision_id(),
                parent_revision=parent,
                written_at_ms=_now_ms(),
            )
            self._conn.execute(
                "INSERT INTO self_projection "
                "(actor_id, revision, parent_revision, written_at_ms, snapshot_json) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(actor_id) DO UPDATE SET "
                " revision=excluded.revision, parent_revision=excluded.parent_revision, "
                " written_at_ms=excluded.written_at_ms, snapshot_json=excluded.snapshot_json",
                (
                    snapshot.actor_id,
                    revision.revision,
                    revision.parent_revision,
                    revision.written_at_ms,
                    json.dumps(body, separators=(",", ":")),
                ),
            )
            self._clear_freshness(f"self:{snapshot.actor_id}")
        return StoreWriteResult(revision=revision, accepted=True)

    # ------------------------------------------------------------------
    # Family
    # ------------------------------------------------------------------
    def read_family(
        self, family_space_id: str
    ) -> tuple[FamilySelfModelSnapshot | None, StoreReadResult]:
        with self._lock:
            row = self._conn.execute(
                "SELECT revision, parent_revision, written_at_ms, snapshot_json "
                "FROM family_projection WHERE family_space_id = ?",
                (family_space_id,),
            ).fetchone()
            freshness = self._read_freshness(f"family:{family_space_id}")
        if row is None:
            return None, StoreReadResult(found=False, freshness=freshness)
        body = json.loads(row["snapshot_json"])
        snapshot = _family_from_json(body)
        revision = ProjectionRevision(
            revision=row["revision"],
            parent_revision=row["parent_revision"] or "",
            written_at_ms=int(row["written_at_ms"]),
        )
        return snapshot, StoreReadResult(found=True, revision=revision, freshness=freshness)

    def write_family(
        self, snapshot: FamilySelfModelSnapshot, *, writer_id: str
    ) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        body = _family_to_json(snapshot)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT revision FROM family_projection WHERE family_space_id = ?",
                (snapshot.family_space_id,),
            ).fetchone()
            parent = row["revision"] if row is not None else ""
            revision = ProjectionRevision(
                revision=_new_revision_id(),
                parent_revision=parent,
                written_at_ms=_now_ms(),
            )
            self._conn.execute(
                "INSERT INTO family_projection "
                "(family_space_id, revision, parent_revision, written_at_ms, snapshot_json) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(family_space_id) DO UPDATE SET "
                " revision=excluded.revision, parent_revision=excluded.parent_revision, "
                " written_at_ms=excluded.written_at_ms, snapshot_json=excluded.snapshot_json",
                (
                    snapshot.family_space_id,
                    revision.revision,
                    revision.parent_revision,
                    revision.written_at_ms,
                    json.dumps(body, separators=(",", ":")),
                ),
            )
            self._clear_freshness(f"family:{snapshot.family_space_id}")
        return StoreWriteResult(revision=revision, accepted=True)

    # ------------------------------------------------------------------
    # Constitution
    # ------------------------------------------------------------------
    def read_constitution(
        self, constitution_id: str
    ) -> tuple[ConstitutionSnapshot | None, StoreReadResult]:
        with self._lock:
            row = self._conn.execute(
                "SELECT version, parent_version, revision, parent_revision, "
                " written_at_ms, snapshot_json "
                "FROM constitution_projection WHERE constitution_id = ?",
                (constitution_id,),
            ).fetchone()
            freshness = self._read_freshness(f"constitution:{constitution_id}")
        if row is None:
            return None, StoreReadResult(found=False, freshness=freshness)
        body = json.loads(row["snapshot_json"])
        snapshot = _constitution_from_json(constitution_id, body)
        revision = ProjectionRevision(
            revision=row["revision"],
            parent_revision=row["parent_revision"] or "",
            written_at_ms=int(row["written_at_ms"]),
        )
        return snapshot, StoreReadResult(found=True, revision=revision, freshness=freshness)

    def write_constitution(
        self, snapshot: ConstitutionSnapshot, *, writer_id: str
    ) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        body = _constitution_to_json(snapshot)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT revision FROM constitution_projection WHERE constitution_id = ?",
                (snapshot.constitution_id,),
            ).fetchone()
            parent = row["revision"] if row is not None else ""
            revision = ProjectionRevision(
                revision=_new_revision_id(),
                parent_revision=parent,
                written_at_ms=_now_ms(),
            )
            payload = json.dumps(body, separators=(",", ":"))
            self._conn.execute(
                "INSERT INTO constitution_projection "
                "(constitution_id, version, parent_version, revision, parent_revision, "
                " written_at_ms, snapshot_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(constitution_id) DO UPDATE SET "
                " version=excluded.version, parent_version=excluded.parent_version, "
                " revision=excluded.revision, parent_revision=excluded.parent_revision, "
                " written_at_ms=excluded.written_at_ms, snapshot_json=excluded.snapshot_json",
                (
                    snapshot.constitution_id,
                    snapshot.version,
                    snapshot.parent_version,
                    revision.revision,
                    revision.parent_revision,
                    revision.written_at_ms,
                    payload,
                ),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO constitution_history "
                "(constitution_id, version, parent_version, written_at_ms, snapshot_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot.constitution_id,
                    snapshot.version,
                    snapshot.parent_version,
                    revision.written_at_ms,
                    payload,
                ),
            )
            self._clear_freshness(f"constitution:{snapshot.constitution_id}")
        return StoreWriteResult(revision=revision, accepted=True)

    # ------------------------------------------------------------------
    # Amendments
    # ------------------------------------------------------------------
    def upsert_amendment(
        self, amendment: AmendmentProposal, *, writer_id: str
    ) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        body = json.dumps(amendment.body, separators=(",", ":"))
        conflict_json = (
            json.dumps(_conflict_to_json(amendment.conflict))
            if amendment.conflict is not None
            else None
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO amendment_proposals "
                "(amendment_id, parent_version, proposed_by, body_json, status, "
                " expires_at_ms, conflict_json, written_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(amendment_id) DO UPDATE SET "
                " parent_version=excluded.parent_version, "
                " proposed_by=excluded.proposed_by, body_json=excluded.body_json, "
                " status=excluded.status, expires_at_ms=excluded.expires_at_ms, "
                " conflict_json=excluded.conflict_json, written_at_ms=excluded.written_at_ms",
                (
                    amendment.amendment_id,
                    amendment.parent_version,
                    amendment.proposed_by,
                    body,
                    amendment.status.value,
                    int(amendment.expires_at_ms),
                    conflict_json,
                    _now_ms(),
                ),
            )
            # Conflict detection: two PENDING amendments sharing parent_version.
            siblings = self._conn.execute(
                "SELECT COUNT(*) AS n FROM amendment_proposals "
                "WHERE parent_version = ? AND status IN ('DRAFT','PENDING')",
                (amendment.parent_version,),
            ).fetchone()["n"]
            reason = ""
            if siblings > 1 and amendment.parent_version:
                # Mark every constitution row as conflict_pending.
                for cid_row in self._conn.execute(
                    "SELECT constitution_id FROM constitution_projection"
                ).fetchall():
                    self._set_freshness(
                        f"constitution:{cid_row['constitution_id']}",
                        ProjectionFreshness.CONFLICT_PENDING,
                    )
                reason = "conflict_pending"
        return StoreWriteResult(
            revision=ProjectionRevision(
                revision=_new_revision_id(),
                written_at_ms=_now_ms(),
            ),
            accepted=True,
            reason=reason,
        )

    def append_signature(
        self,
        amendment_id: str,
        signature: SigningProof,
        *,
        writer_id: str,
    ) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT amendment_id FROM amendment_proposals WHERE amendment_id = ?",
                (amendment_id,),
            ).fetchone()
            if row is None:
                return StoreWriteResult(
                    revision=ProjectionRevision(),
                    accepted=False,
                    reason="amendment_not_found",
                )
            try:
                self._conn.execute(
                    "INSERT INTO amendment_signatures "
                    "(amendment_id, signer_id, key_id, algorithm, signature_b64, signed_at_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        amendment_id,
                        signature.signer_id,
                        signature.key_id,
                        signature.algorithm,
                        signature.signature_b64,
                        int(signature.signed_at_ms),
                    ),
                )
            except sqlite3.IntegrityError:
                return StoreWriteResult(
                    revision=ProjectionRevision(),
                    accepted=False,
                    reason="duplicate_signer",
                )
        return StoreWriteResult(
            revision=ProjectionRevision(
                revision=_new_revision_id(),
                written_at_ms=_now_ms(),
            ),
            accepted=True,
        )

    def get_amendment(self, amendment_id: str) -> AmendmentProposal | None:
        """Test helper / re-hydrator used by services to refresh state."""
        with self._lock:
            row = self._conn.execute(
                "SELECT amendment_id, parent_version, proposed_by, body_json, status, "
                " expires_at_ms, conflict_json "
                "FROM amendment_proposals WHERE amendment_id = ?",
                (amendment_id,),
            ).fetchone()
            if row is None:
                return None
            sig_rows = self._conn.execute(
                "SELECT signer_id, key_id, algorithm, signature_b64, signed_at_ms "
                "FROM amendment_signatures WHERE amendment_id = ? "
                "ORDER BY signed_at_ms ASC",
                (amendment_id,),
            ).fetchall()
        signatures = tuple(
            SigningProof(
                signer_id=s["signer_id"],
                key_id=s["key_id"],
                algorithm=s["algorithm"],
                signature_b64=s["signature_b64"],
                signed_at_ms=int(s["signed_at_ms"]),
            )
            for s in sig_rows
        )
        conflict = (
            _conflict_from_json(json.loads(row["conflict_json"]))
            if row["conflict_json"]
            else None
        )
        return AmendmentProposal(
            amendment_id=row["amendment_id"],
            parent_version=row["parent_version"] or "",
            proposed_by=row["proposed_by"],
            body=json.loads(row["body_json"]),
            status=AmendmentStatus(row["status"]),
            signatures=signatures,
            expires_at_ms=int(row["expires_at_ms"]),
            conflict=conflict,
        )

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------
    def freshness(self, projection_key: str) -> ProjectionFreshness:
        with self._lock:
            return self._read_freshness(projection_key)

    def mark_stale(self, projection_key: str) -> None:
        with self._lock:
            self._set_freshness(projection_key, ProjectionFreshness.STALE)

    def mark_offline_local_only(self, projection_key: str) -> None:
        with self._lock:
            self._set_freshness(projection_key, ProjectionFreshness.OFFLINE_LOCAL_ONLY)

    def clear_freshness(self, projection_key: str) -> None:
        with self._lock:
            self._clear_freshness(projection_key)

    # ------------------------------------------------------------------
    # Internal freshness helpers
    # ------------------------------------------------------------------
    def _read_freshness(self, projection_key: str) -> ProjectionFreshness:
        row = self._conn.execute(
            "SELECT freshness FROM projection_sync_state WHERE projection_key = ?",
            (projection_key,),
        ).fetchone()
        if row is None:
            return ProjectionFreshness.FRESH
        try:
            return ProjectionFreshness(row["freshness"])
        except ValueError:
            return ProjectionFreshness.FRESH

    def _set_freshness(
        self, projection_key: str, freshness: ProjectionFreshness
    ) -> None:
        self._conn.execute(
            "INSERT INTO projection_sync_state "
            "(projection_key, freshness, last_synced_at_ms, last_revision) "
            "VALUES (?, ?, ?, '') "
            "ON CONFLICT(projection_key) DO UPDATE SET "
            " freshness=excluded.freshness, last_synced_at_ms=excluded.last_synced_at_ms",
            (projection_key, freshness.value, _now_ms()),
        )

    def _clear_freshness(self, projection_key: str) -> None:
        self._conn.execute(
            "DELETE FROM projection_sync_state WHERE projection_key = ?",
            (projection_key,),
        )

    # ------------------------------------------------------------------
    # Identity-session helper (composed by SQLiteSessionStore)
    # ------------------------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the connection for sibling adapters (e.g. SQLiteSessionStore)."""
        return self._conn

    @property
    def write_lock(self) -> threading.RLock:
        return self._lock


# ---------------------------------------------------------------------
# Identity-session SQLite store (sibling of the projection store)
# ---------------------------------------------------------------------
class SQLiteSessionStore(IIdentitySessionStore):
    """Identity sessions table accessed through ``SQLiteProjectionStore``."""

    def __init__(self, projection_store: SQLiteProjectionStore) -> None:
        self._projection = projection_store

    def put(self, session: IdentitySession) -> None:
        with self._projection.write_lock, self._projection.connection:
            self._projection.connection.execute(
                "INSERT INTO identity_sessions "
                "(session_token, profile_id, tier, device_id, "
                " issued_at_ms, hard_expires_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_token) DO UPDATE SET "
                " tier=excluded.tier, hard_expires_at_ms=excluded.hard_expires_at_ms",
                (
                    session.session_token,
                    session.profile_id,
                    int(session.tier),
                    session.device_id,
                    int(session.issued_at_ms),
                    int(session.hard_expires_at_ms),
                ),
            )

    def get(self, token: str) -> IdentitySession | None:
        with self._projection.write_lock:
            row = self._projection.connection.execute(
                "SELECT session_token, profile_id, tier, device_id, "
                " issued_at_ms, hard_expires_at_ms "
                "FROM identity_sessions WHERE session_token = ?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        return IdentitySession(
            session_token=row["session_token"],
            profile_id=row["profile_id"],
            tier=IdentityTier(int(row["tier"])),
            device_id=row["device_id"],
            issued_at_ms=int(row["issued_at_ms"]),
            hard_expires_at_ms=int(row["hard_expires_at_ms"]),
        )

    def delete(self, token: str) -> None:
        with self._projection.write_lock, self._projection.connection:
            self._projection.connection.execute(
                "DELETE FROM identity_sessions WHERE session_token = ?",
                (token,),
            )

    def purge_expired(self, *, now_ms: int) -> int:
        with self._projection.write_lock, self._projection.connection:
            cur = self._projection.connection.execute(
                "DELETE FROM identity_sessions WHERE hard_expires_at_ms > 0 "
                "AND hard_expires_at_ms <= ?",
                (now_ms,),
            )
            return cur.rowcount or 0


# ---------------------------------------------------------------------
# Snapshot ↔ JSON helpers
# ---------------------------------------------------------------------
def _self_to_json(snapshot: K1SelfModelSnapshot) -> dict:
    return {
        "actor_id": snapshot.actor_id,
        "revision": snapshot.revision,
        "L1_core": dict(snapshot.L1_core),
        "L2_identity": dict(snapshot.L2_identity),
        "L3_pattern": dict(snapshot.L3_pattern),
        "L4_context": {},
        "L5_state": {},
        "composed_at_ms": int(snapshot.composed_at_ms),
    }


def _self_from_json(body: dict) -> K1SelfModelSnapshot:
    return K1SelfModelSnapshot(
        actor_id=body.get("actor_id", ""),
        revision=body.get("revision", ""),
        L1_core=dict(body.get("L1_core") or {}),
        L2_identity=dict(body.get("L2_identity") or {}),
        L3_pattern=dict(body.get("L3_pattern") or {}),
        L4_context={},
        L5_state={},
        composed_at_ms=int(body.get("composed_at_ms", 0)),
    )


def _family_to_json(snapshot: FamilySelfModelSnapshot) -> dict:
    return {
        "family_space_id": snapshot.family_space_id,
        "revision": snapshot.revision,
        "members": [
            {
                "member_id": m.member_id,
                "display_name": m.display_name,
                "role": m.role,
                "age_band": m.age_band,
            }
            for m in snapshot.members
        ],
        "relations": [
            {
                "from_member": r.from_member,
                "to_member": r.to_member,
                "kind": r.kind,
                "weight": float(r.weight),
            }
            for r in snapshot.relations
        ],
        "routines": [
            {"routine_id": rt.routine_id, "name": rt.name, "schedule": rt.schedule}
            for rt in snapshot.routines
        ],
        "composed_at_ms": int(snapshot.composed_at_ms),
    }


def _family_from_json(body: dict) -> FamilySelfModelSnapshot:
    from k1.selfmodel.contracts.family_model import (
        FamilyMemberRef,
        FamilySelfModelSnapshot as _Snap,
        RelationshipEdge,
        RoutineRef,
    )

    members = tuple(
        FamilyMemberRef(
            member_id=m.get("member_id", ""),
            display_name=m.get("display_name", ""),
            role=m.get("role", ""),
            age_band=m.get("age_band", ""),
        )
        for m in body.get("members") or ()
    )
    relations = tuple(
        RelationshipEdge(
            from_member=r.get("from_member", ""),
            to_member=r.get("to_member", ""),
            kind=r.get("kind", ""),
            weight=float(r.get("weight", 1.0)),
        )
        for r in body.get("relations") or ()
    )
    routines = tuple(
        RoutineRef(
            routine_id=rt.get("routine_id", ""),
            name=rt.get("name", ""),
            schedule=rt.get("schedule", ""),
        )
        for rt in body.get("routines") or ()
    )
    return _Snap(
        family_space_id=body.get("family_space_id", ""),
        revision=body.get("revision", ""),
        members=members,
        relations=relations,
        routines=routines,
        composed_at_ms=int(body.get("composed_at_ms", 0)),
    )


def _constitution_to_json(snapshot: ConstitutionSnapshot) -> dict:
    return {
        "version": snapshot.version,
        "parent_version": snapshot.parent_version,
        "body": dict(snapshot.body),
        "signatures": [
            {
                "signer_id": s.signer_id,
                "key_id": s.key_id,
                "algorithm": s.algorithm,
                "signature_b64": s.signature_b64,
                "signed_at_ms": int(s.signed_at_ms),
            }
            for s in snapshot.signatures
        ],
        "activated_at_ms": int(snapshot.activated_at_ms),
    }


def _constitution_from_json(constitution_id: str, body: dict) -> ConstitutionSnapshot:
    sigs = tuple(
        SigningProof(
            signer_id=s.get("signer_id", ""),
            key_id=s.get("key_id", ""),
            algorithm=s.get("algorithm", "ed25519"),
            signature_b64=s.get("signature_b64", ""),
            signed_at_ms=int(s.get("signed_at_ms", 0)),
        )
        for s in body.get("signatures") or ()
    )
    return ConstitutionSnapshot(
        constitution_id=constitution_id,
        version=body.get("version", ""),
        parent_version=body.get("parent_version", ""),
        body=dict(body.get("body") or {}),
        signatures=sigs,
        activated_at_ms=int(body.get("activated_at_ms", 0)),
    )


def _conflict_to_json(c: ConflictDescriptor) -> dict:
    return {
        "parent_version": c.parent_version,
        "sibling_amendment_ids": list(c.sibling_amendment_ids),
        "detected_at_ms": int(c.detected_at_ms),
    }


def _conflict_from_json(body: dict) -> ConflictDescriptor:
    return ConflictDescriptor(
        parent_version=body.get("parent_version", ""),
        sibling_amendment_ids=tuple(body.get("sibling_amendment_ids") or ()),
        detected_at_ms=int(body.get("detected_at_ms", 0)),
    )
