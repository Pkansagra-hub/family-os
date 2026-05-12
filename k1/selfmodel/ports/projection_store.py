"""``IProjectionStorePort`` — durable read/write of the five-layer projection.

ABC (mutating), matching ``k1.sessionstate.ports.writer.IWriterPort``
discipline. Production implementation in M3
(``adapters/sqlite_projection_store.py``); test double in M0
(``adapters/memory_projection_store.py``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.contracts.space_graph import SpaceGraphSnapshot

__all__ = [
    "ProjectionFreshness",
    "ProjectionRevision",
    "StoreReadResult",
    "StoreWriteResult",
    "IProjectionStorePort",
]


class ProjectionFreshness(str, Enum):
    """Freshness of a stored projection at read time."""

    FRESH = "fresh"
    STALE = "stale"
    OFFLINE_LOCAL_ONLY = "offline_local_only"
    CONFLICT_PENDING = "conflict_pending"


@dataclass(frozen=True)
class ProjectionRevision:
    """Opaque version handle for a projection row."""

    revision: str = ""
    parent_revision: str = ""
    written_at_ms: int = 0


@dataclass(frozen=True)
class StoreReadResult:
    """Result of a projection read."""

    found: bool
    revision: ProjectionRevision = ProjectionRevision()
    freshness: ProjectionFreshness = ProjectionFreshness.FRESH


@dataclass(frozen=True)
class StoreWriteResult:
    """Result of a projection write."""

    revision: ProjectionRevision
    accepted: bool = True
    reason: str = ""


class IProjectionStorePort(ABC):
    """Persistent store for self / family / constitution projections.

    Mutating ABC. Implementations enforce single-writer discipline by
    rejecting unauthorized ``writer_id`` values. ``L4_context`` and
    ``L5_state`` blocks of ``K1SelfModelSnapshot`` are RAM-only and
    MUST NOT be persisted.
    """

    # ---- Self ----------------------------------------------------------
    @abstractmethod
    def read_self(self, actor_id: str) -> tuple[K1SelfModelSnapshot | None, StoreReadResult]:
        """Read the persisted self projection for ``actor_id``."""

    @abstractmethod
    def write_self(self, snapshot: K1SelfModelSnapshot, *, writer_id: str) -> StoreWriteResult:
        """Persist ``snapshot`` (L1/L2/L3 only; L4/L5 are dropped)."""

    # ---- Space graph -----------------------------------------------
    @abstractmethod
    def read_space(self, space_id: str) -> tuple[SpaceGraphSnapshot | None, StoreReadResult]:
        """Read the persisted space-graph projection."""

    @abstractmethod
    def write_space(self, snapshot: SpaceGraphSnapshot, *, writer_id: str) -> StoreWriteResult:
        """Persist the space-graph projection."""

    # ---- Constitution --------------------------------------------------
    @abstractmethod
    def read_constitution(
        self, constitution_id: str
    ) -> tuple[ConstitutionSnapshot | None, StoreReadResult]:
        """Read the active constitution snapshot."""

    @abstractmethod
    def write_constitution(
        self, snapshot: ConstitutionSnapshot, *, writer_id: str
    ) -> StoreWriteResult:
        """Persist a new constitution snapshot (immutable row)."""

    # ---- Amendments ----------------------------------------------------
    @abstractmethod
    def upsert_amendment(self, amendment: AmendmentProposal, *, writer_id: str) -> StoreWriteResult:
        """Insert or update an amendment proposal row."""

    @abstractmethod
    def append_signature(
        self, amendment_id: str, signature: SigningProof, *, writer_id: str
    ) -> StoreWriteResult:
        """Append a signature row (append-only)."""

    # ---- Freshness -----------------------------------------------------
    @abstractmethod
    def freshness(self, projection_key: str) -> ProjectionFreshness:
        """Current freshness for an arbitrary projection key."""
