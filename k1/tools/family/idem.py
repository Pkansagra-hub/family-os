"""
k1.tools.family.idem -- SQLite-backed idempotency store.

The store dedupes ``BaseToolService.dispatch`` calls by
``(adapter_id, action, idem_key, space_id)`` so a caller (LLM,
scheduler, UI retry) can safely repeat the same write request and
receive the same response without producing a duplicate side-effect.

Design
------
* One row per (adapter_id, action, idem_key, space_id).  ``space_id``
  is part of the key so two households can each carry the same
  caller-supplied idempotency key without collision.
* The result of the original call is stored as JSON; replays return the
  stored row verbatim (status, result, timestamp).
* Entries are TTL-bound; ``_TTL_S`` defaults to 24 hours, after which a
  row is no longer considered a replay (and any subsequent record() for
  the same key over-writes the stale entry).

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.5.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

# 24 hours in seconds.  Aligned with the M14 outbox retention default so
# a downstream cold-sync replay window doesn't surface idempotency
# semantics that have already lapsed in the K1 store.
_TTL_S: int = 24 * 60 * 60


_DDL: str = """
CREATE TABLE IF NOT EXISTS tool_idem (
    adapter_id  TEXT NOT NULL,
    action      TEXT NOT NULL,
    idem_key    TEXT NOT NULL,
    space_id    TEXT NOT NULL,
    status      TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (adapter_id, action, idem_key, space_id)
);
"""


class IdempotencyStore:
    """Read/record idempotency entries for family-tool dispatches.

    The store does NOT manage the underlying ``sqlite3.Connection`` --
    that lifecycle belongs to :class:`K1FamilyStore`.  Pass a connection
    opened with ``check_same_thread=False`` so the same store can be
    consulted from the asyncio event loop and from background threads.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        with self._conn:
            self._conn.executescript(_DDL)

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def lookup(
        self,
        adapter_id: str,
        action: str,
        idem_key: str,
        space_id: str,
    ) -> Optional[dict[str, Any]]:
        """Return the stored result for a key tuple if still within TTL.

        Returns ``None`` when no row exists OR when the row has expired
        (older than ``_TTL_S``).  Expired rows are not deleted here --
        :meth:`record` will overwrite them on the next call.
        """

        row = self._conn.execute(
            """
            SELECT status, result_json, created_at
            FROM tool_idem
            WHERE adapter_id = ?
              AND action = ?
              AND idem_key = ?
              AND space_id = ?
            """,
            (adapter_id, action, idem_key, space_id),
        ).fetchone()

        if row is None:
            return None

        status, result_json, created_at = row
        if (time.time() - float(created_at)) > _TTL_S:
            return None

        try:
            result = json.loads(result_json)
        except Exception:
            # Corrupt row; treat as absent so the dispatch proceeds.
            return None

        return {
            "status": status,
            "result": result,
            "created_at": int(created_at),
        }

    # ------------------------------------------------------------------ #
    # Record
    # ------------------------------------------------------------------ #

    def record(
        self,
        adapter_id: str,
        action: str,
        idem_key: str,
        space_id: str,
        status: str,
        result: dict[str, Any],
    ) -> None:
        """Persist the outcome of a dispatch under the key tuple.

        Uses ``INSERT OR REPLACE`` so a successful retry after a TTL
        expiry transparently overwrites the stale row.
        """

        result_json = json.dumps(result, default=str)
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO tool_idem
                    (adapter_id, action, idem_key, space_id, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adapter_id,
                    action,
                    idem_key,
                    space_id,
                    status,
                    result_json,
                    int(time.time()),
                ),
            )
