"""
k1.tools.family.base -- ``BaseEntity`` and ``WriteContext`` primitives.

These are the two contracts every family tool service is built around:

* ``BaseEntity`` -- the immutable record shape persisted by every family
  tool service.  Subclasses (``CalendarEvent``, ``HealthVital``) add
  typed business fields; the universal columns defined here -- id,
  space_id, source, source_label, actor (creator), visibility, version,
  tags, metadata, created_at/updated_at/deleted_at -- support
  row-level ACL, optimistic concurrency, soft-delete, audit trail, and
  cross-tool linkage uniformly across every adapter.

* ``WriteContext`` -- the per-call frame that carries the requesting
  actor's identity, household scope, role, safety-band, idempotency
  key, and trace correlation.

Both types use Pydantic v2 with ``extra="forbid"`` (unknown fields fail
fast) and are ``frozen=True`` so persisted records cannot mutate -- new
revisions are produced via ``model_copy(update=...)`` (or, for
``BaseEntity``, ``bump(actor)``).

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.1
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Canonical vocabularies
# ---------------------------------------------------------------------------

Role = Literal["parent", "child", "guardian", "elder", "system", "guest"]
"""Caller role vocabulary.

Ordering used for ``min_role`` gates (higher number = stronger
privilege): ``system=5 > parent=4 > guardian=3 > elder=2 > child=1 >
guest=0``.
"""

# Ordering table consumed by ``role_satisfies`` and BaseToolService.
_ROLE_ORDER: dict[str, int] = {
    "guest": 0,
    "child": 1,
    "elder": 2,
    "guardian": 3,
    "parent": 4,
    "system": 5,
}


def role_satisfies(actor: str, required: str) -> bool:
    """Return True iff ``actor`` role >= ``required`` role in the privilege ladder.

    Unknown actors compare as below ``guest``; unknown required levels
    default to ``parent`` (fail-closed for typos in declarations).
    """

    return _ROLE_ORDER.get(actor, -1) >= _ROLE_ORDER.get(required, _ROLE_ORDER["parent"])


Visibility = Literal["family", "adults", "named", "private"]
"""Row-level visibility band.

* ``family``  -- visible to every household member (parent/child/guardian/elder) and ``system``.
* ``adults``  -- visible to adults only (parent/guardian/elder/system).
* ``named``   -- restricted to an explicit ``named_visible`` allow-list on the row.
* ``private`` -- only the row's creator (``BaseEntity.actor``) can read it.
"""

SourceKind = Literal[
    "native",
    "google",
    "outlook",
    "teams",
    "classroom",
    "apple",
    "manual_import",
    "system_generated",
]
"""Provenance of a persisted entity."""


def _now_utc() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# BaseEntity
# ---------------------------------------------------------------------------


class BaseEntity(BaseModel):
    """Immutable base class for every persisted family-tool record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # ---- Identity & scope ----
    id: str = Field(..., min_length=1, description="Stable record identifier.")
    space_id: str = Field(default="", description="Household scope identifier.")

    # ---- Provenance ----
    source: SourceKind = Field(default="native", description="Where the record originated.")
    source_label: str = Field(default="", description="Free-form sub-label for ``source``.")
    actor: str = Field(default="", description="``member_id`` of the user who created the row.")

    # ---- Visibility & ACL extension ----
    visibility: Visibility = Field(default="family", description="Row-level visibility band.")
    named_visible: list[str] = Field(
        default_factory=list,
        description="``member_id`` allow-list consulted when ``visibility='named'``.",
    )

    # ---- Audit trail ----
    version: int = Field(default=1, ge=1, description="Monotonic per-record revision counter.")
    created_at: datetime = Field(default_factory=_now_utc, description="UTC creation timestamp.")
    updated_at: datetime = Field(
        default_factory=_now_utc, description="UTC timestamp of the most recent revision."
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when soft-deleted; ``None`` for live rows.",
    )

    # ---- Optional descriptive bag ----
    tags: list[str] = Field(default_factory=list, description="Free-form classification tags.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-private metadata blob; opaque to the foundation.",
    )

    # ------------------------------------------------------------------ #
    # Convenience helpers
    # ------------------------------------------------------------------ #

    @property
    def is_deleted(self) -> bool:
        """Whether the entity is soft-deleted."""

        return self.deleted_at is not None

    def to_storage_row(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict suitable for SQLite persistence."""

        return self.model_dump(mode="json")

    def bump(self, actor: str) -> "BaseEntity":
        """Return a new revision of this entity with ``version+1`` and refreshed ``updated_at``."""

        new_meta = dict(self.metadata)
        new_meta["_last_actor"] = actor
        return self.model_copy(
            update={
                "version": self.version + 1,
                "updated_at": _now_utc(),
                "metadata": new_meta,
            }
        )


# ---------------------------------------------------------------------------
# WriteContext
# ---------------------------------------------------------------------------


Face = Literal["llm", "ui", "voice", "scheduler", "system"]
"""Which surface drove the inbound dispatch."""


class WriteContext(BaseModel):
    """Per-call frame carried into every service action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # ---- Caller identity ----
    user_id: str = Field(..., min_length=1, description="Caller user identifier.")
    space_id: str = Field(default="", description="Household scope identifier.")
    role: Role = Field(default="parent", description="Caller's effective role.")

    # ---- Session / trace ----
    session_id: Optional[str] = Field(default=None, description="Originating session identifier.")
    trace_id: str = Field(..., min_length=1, description="Cross-component correlation identifier.")
    face: Face = Field(default="system", description="Surface that drove the dispatch.")

    # ---- Safety + reliability ----
    band: Literal["GREEN", "AMBER", "RED", "CRISIS"] = Field(
        default="GREEN",
        description="Live safety band (aligned to ``k1.fabric.types.SafetyBand``).",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional caller-supplied dedupe key for write actions.",
    )

    # ---- Time + extras ----
    now: datetime = Field(default_factory=_now_utc, description="Logical time-of-call (UTC).")
    extras: dict[str, Any] = Field(default_factory=dict, description="Forward-compatible bag.")

    # ------------------------------------------------------------------ #
    # Plan-vocabulary aliases (read-only)
    # ------------------------------------------------------------------ #

    @property
    def actor_member_id(self) -> str:
        return self.user_id

    @property
    def actor_role(self) -> Role:
        return self.role

    @property
    def idem_key(self) -> Optional[str]:
        return self.idempotency_key
