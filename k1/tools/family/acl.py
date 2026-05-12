"""
k1.tools.family.acl -- row-level ACL evaluator.

``filter_rows`` is the single chokepoint every family-tool *read* action
runs untrusted-rows-from-storage through before returning them to the
caller.  Centralising the check guarantees the soft-delete + visibility
+ ownership logic stays uniform across every adapter (Calendar, Health,
Finance, IoT) and that auditing/tests need to cover only one
implementation.

Visibility semantics (matches :data:`k1.tools.family.base.Visibility`):

* ``family``  -- visible to every household member (parent / child /
                 guardian / elder) plus ``system``.  Not visible to
                 ``guest``.
* ``adults``  -- visible to parents / guardians / elders / system only;
                 children and guests do NOT see these rows.
* ``named``   -- restricted to the row's ``named_visible`` allow-list of
                 ``member_id`` values.  Falls back to ``private`` semantics
                 when the allow-list is empty.
* ``private`` -- only the row's ``actor`` (creator) can read it.

The evaluator is pure / synchronous / dependency-free.  Soft-deleted
rows are dropped by default; callers that need to surface tombstones
(admin tooling) pass ``include_deleted=True``.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from k1.tools.family.base import WriteContext
from k1.tools.family.policy import VisibilityPolicy, default_policy

# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def _row_actor(row: dict[str, Any]) -> Optional[str]:
    """Return the row's creator ``member_id``, or ``None`` if absent."""

    val = row.get("actor")
    if isinstance(val, str) and val:
        return val
    # Backwards-compat: tests / pre-foundation rows used ``user_id``.
    legacy = row.get("user_id")
    return legacy if isinstance(legacy, str) and legacy else None


def _row_space(row: dict[str, Any]) -> str:
    """Return the row's ``space_id`` (household scope), defaulting to empty string."""

    val = row.get("space_id")
    return val if isinstance(val, str) else ""


def _row_visibility(row: dict[str, Any]) -> str:
    """Return the row's visibility band, defaulting to ``"private"``."""

    val = row.get("visibility")
    return val if isinstance(val, str) and val else "private"


def _row_named_visible(row: dict[str, Any]) -> list[str]:
    """Return the row's ``named_visible`` allow-list, defaulting to empty."""

    val = row.get("named_visible")
    if isinstance(val, list):
        return [v for v in val if isinstance(v, str)]
    return []


def _row_is_deleted(row: dict[str, Any]) -> bool:
    """Return True iff the row carries a non-null ``deleted_at`` marker."""

    return row.get("deleted_at") is not None


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def filter_rows(
    rows: Iterable[dict[str, Any]],
    ctx: WriteContext,
    policy: Optional[VisibilityPolicy] = None,
    *,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Return only those rows the caller in ``ctx`` may read.

    Decision order (cheapest gate first):

    1. Soft-delete -- drop rows with non-null ``deleted_at`` unless
       ``include_deleted=True``.
    2. Space scope -- when ``ctx.space_id`` is set, drop rows whose
       ``space_id`` is set and differs (rows with empty ``space_id``
       are treated as global-to-caller).
    3. Visibility band -- drop rows whose ``visibility`` is not in the
       caller-role's visible set (see ``VisibilityPolicy``).
    4. Per-band ownership:
       * ``private`` -- only the row's ``actor`` (creator) passes,
         unless the caller has cross-user-read privilege.
       * ``named``   -- caller's ``user_id`` must be present in
         ``named_visible``; falls back to ``private`` semantics when
         that list is empty.
       * ``family`` / ``adults`` -- already gated by the visibility band
         table; no further owner check.
    """

    pol = policy or default_policy()
    visible = pol.visible_bands_for(ctx.role)
    cross_user_ok = pol.can_read_cross_user(ctx.role)
    caller_space = ctx.space_id

    out: list[dict[str, Any]] = []
    for row in rows:
        # 1. soft-delete
        if not include_deleted and _row_is_deleted(row):
            continue

        # 2. space scope (best-effort: empty caller space disables the gate)
        if caller_space:
            row_space = _row_space(row)
            if row_space and row_space != caller_space:
                continue

        # 3. visibility band
        vis = _row_visibility(row)
        if vis not in visible:
            continue

        # 4. per-band ownership
        if vis == "private":
            if not cross_user_ok:
                if _row_actor(row) != ctx.user_id:
                    continue
        elif vis == "named":
            allow = _row_named_visible(row)
            if not allow:
                # Empty allow-list -> private semantics.
                if not cross_user_ok and _row_actor(row) != ctx.user_id:
                    continue
            elif ctx.user_id not in allow:
                if not cross_user_ok:
                    continue
        # vis in {"family", "adults"}: already gated by visible-set above.

        out.append(row)

    return out
