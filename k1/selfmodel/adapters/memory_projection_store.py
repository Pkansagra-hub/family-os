"""``InMemoryProjectionStore`` — RAM-only ``IProjectionStorePort`` for tests.

Production store is ``SQLiteProjectionStore`` (M3.E4); this double
keeps the same surface so every higher-level service can be unit-tested
without touching disk. Conflict detection is intentionally simplistic
(parent_version / parent_revision mismatch on amendments) — sufficient
for invariant tests; the SQLite store will tighten the rules.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import replace

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.contracts.space_graph import SpaceGraphSnapshot
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
    ProjectionRevision,
    StoreReadResult,
    StoreWriteResult,
)

__all__ = ["InMemoryProjectionStore"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_revision(parent: str = "") -> ProjectionRevision:
    return ProjectionRevision(
        revision=uuid.uuid4().hex,
        parent_revision=parent,
        written_at_ms=_now_ms(),
    )


class InMemoryProjectionStore(IProjectionStorePort):
    """Thread-safe in-memory implementation of the projection store."""

    def __init__(self, *, allowed_writers: tuple[str, ...] | None = None) -> None:
        self._lock = threading.RLock()
        self._allowed_writers = frozenset(allowed_writers) if allowed_writers is not None else None
        # key -> (snapshot, revision)
        self._self: dict[str, tuple[K1SelfModelSnapshot, ProjectionRevision]] = {}
        self._space: dict[str, tuple[SpaceGraphSnapshot, ProjectionRevision]] = {}
        self._constitution: dict[str, tuple[ConstitutionSnapshot, ProjectionRevision]] = {}
        # Amendments are keyed by amendment_id; signatures are appended.
        self._amendments: dict[str, AmendmentProposal] = {}
        # Conflict tracking: constitution_id -> set[parent_version]
        self._pending_parents: dict[str, dict[str, set[str]]] = {}
        # Per-projection-key freshness override (only set by helpers).
        self._freshness: dict[str, ProjectionFreshness] = {}

    # ------------------------------------------------------------------
    # Helpers (test-only mutators)
    # ------------------------------------------------------------------
    def mark_stale(self, projection_key: str) -> None:
        """Mark ``projection_key`` as STALE for read-side freshness tests."""
        with self._lock:
            self._freshness[projection_key] = ProjectionFreshness.STALE

    def mark_offline_local_only(self, projection_key: str) -> None:
        """Mark ``projection_key`` as OFFLINE_LOCAL_ONLY."""
        with self._lock:
            self._freshness[projection_key] = ProjectionFreshness.OFFLINE_LOCAL_ONLY

    def clear_freshness(self, projection_key: str) -> None:
        """Drop the freshness override (back to FRESH)."""
        with self._lock:
            self._freshness.pop(projection_key, None)

    # ------------------------------------------------------------------
    # Writer-id authorization
    # ------------------------------------------------------------------
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
    def read_self(self, actor_id: str) -> tuple[K1SelfModelSnapshot | None, StoreReadResult]:
        key = f"self:{actor_id}"
        with self._lock:
            entry = self._self.get(actor_id)
            if entry is None:
                return None, StoreReadResult(
                    found=False, freshness=self._freshness.get(key, ProjectionFreshness.FRESH)
                )
            snapshot, revision = entry
            return snapshot, StoreReadResult(
                found=True,
                revision=revision,
                freshness=self._freshness.get(key, ProjectionFreshness.FRESH),
            )

    def write_self(self, snapshot: K1SelfModelSnapshot, *, writer_id: str) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        # L4/L5 are RAM-only and MUST NOT be persisted.
        cleaned = replace(snapshot, L4_context={}, L5_state={})
        with self._lock:
            prev = self._self.get(snapshot.actor_id)
            parent = prev[1].revision if prev is not None else ""
            revision = _new_revision(parent=parent)
            self._self[snapshot.actor_id] = (cleaned, revision)
            self._freshness.pop(f"self:{snapshot.actor_id}", None)
            return StoreWriteResult(revision=revision, accepted=True)

    # ------------------------------------------------------------------
    # Space graph
    # ------------------------------------------------------------------
    def read_space(self, space_id: str) -> tuple[SpaceGraphSnapshot | None, StoreReadResult]:
        key = f"space:{space_id}"
        with self._lock:
            entry = self._space.get(space_id)
            if entry is None:
                return None, StoreReadResult(
                    found=False, freshness=self._freshness.get(key, ProjectionFreshness.FRESH)
                )
            snapshot, revision = entry
            return snapshot, StoreReadResult(
                found=True,
                revision=revision,
                freshness=self._freshness.get(key, ProjectionFreshness.FRESH),
            )

    def write_space(self, snapshot: SpaceGraphSnapshot, *, writer_id: str) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        with self._lock:
            prev = self._space.get(snapshot.space_id)
            parent = prev[1].revision if prev is not None else ""
            revision = _new_revision(parent=parent)
            self._space[snapshot.space_id] = (snapshot, revision)
            self._freshness.pop(f"space:{snapshot.space_id}", None)
            return StoreWriteResult(revision=revision, accepted=True)

    # ------------------------------------------------------------------
    # Constitution
    # ------------------------------------------------------------------
    def read_constitution(
        self, constitution_id: str
    ) -> tuple[ConstitutionSnapshot | None, StoreReadResult]:
        key = f"constitution:{constitution_id}"
        with self._lock:
            entry = self._constitution.get(constitution_id)
            if entry is None:
                return None, StoreReadResult(
                    found=False, freshness=self._freshness.get(key, ProjectionFreshness.FRESH)
                )
            snapshot, revision = entry
            return snapshot, StoreReadResult(
                found=True,
                revision=revision,
                freshness=self._freshness.get(key, ProjectionFreshness.FRESH),
            )

    def write_constitution(
        self, snapshot: ConstitutionSnapshot, *, writer_id: str
    ) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        with self._lock:
            prev = self._constitution.get(snapshot.constitution_id)
            parent = prev[1].revision if prev is not None else ""
            revision = _new_revision(parent=parent)
            self._constitution[snapshot.constitution_id] = (snapshot, revision)
            self._freshness.pop(f"constitution:{snapshot.constitution_id}", None)
            return StoreWriteResult(revision=revision, accepted=True)

    # ------------------------------------------------------------------
    # Amendments
    # ------------------------------------------------------------------
    def upsert_amendment(self, amendment: AmendmentProposal, *, writer_id: str) -> StoreWriteResult:
        denial = self._check_writer(writer_id)
        if denial is not None:
            return denial
        with self._lock:
            self._amendments[amendment.amendment_id] = amendment
            # Conflict detection: two distinct PENDING amendments with the
            # same parent_version flag the chain as CONFLICT_PENDING.
            siblings = self._pending_parents.setdefault("__global__", {}).setdefault(
                amendment.parent_version, set()
            )
            siblings.add(amendment.amendment_id)
            reason = ""
            if len(siblings) > 1:
                # Mark every constitution row as conflict_pending; the
                # service layer will reconcile.
                for cid in self._constitution:
                    self._freshness[f"constitution:{cid}"] = ProjectionFreshness.CONFLICT_PENDING
                reason = "conflict_pending"
            revision = _new_revision()
            return StoreWriteResult(revision=revision, accepted=True, reason=reason)

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
        with self._lock:
            existing = self._amendments.get(amendment_id)
            if existing is None:
                return StoreWriteResult(
                    revision=ProjectionRevision(),
                    accepted=False,
                    reason="amendment_not_found",
                )
            updated = replace(existing, signatures=(*existing.signatures, signature))
            self._amendments[amendment_id] = updated
            return StoreWriteResult(revision=_new_revision(), accepted=True)

    def get_amendment(self, amendment_id: str) -> AmendmentProposal | None:
        """Test helper — reads an amendment back."""
        with self._lock:
            return self._amendments.get(amendment_id)

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------
    def freshness(self, projection_key: str) -> ProjectionFreshness:
        with self._lock:
            return self._freshness.get(projection_key, ProjectionFreshness.FRESH)
