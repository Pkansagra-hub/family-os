"""IdempotencyStore — prevents duplicate capability execution.

Phase 1, Epic 1 (Issue 1.6).  Per whiteboard Component 3.
State machine: not_seen → in_flight → succeeded/failed.
``succeeded`` is immutable — enforced via SQL WHERE clause.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IdempotencyCheckResult:
    state: str  # "not_seen" | "in_flight" | "succeeded" | "failed"
    prior_observation: dict | None
    error: str | None


class IdempotencyStore:
    """Shared SQLite store for idempotency key tracking."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def open(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("IdempotencyStore is not open")
        return self._conn

    # ── Schema ─────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                idempotency_key TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'not_seen'
                    CHECK(state IN ('not_seen','in_flight','succeeded','failed')),
                invocation_id TEXT NOT NULL DEFAULT '',
                observation_json TEXT NOT NULL DEFAULT '{}',
                error TEXT,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """)

    # ── State machine ──────────────────────────────────────────────────

    def check(self, idempotency_key: str) -> IdempotencyCheckResult:
        import json

        row = self._db.execute(
            "SELECT state, observation_json, error FROM idempotency_keys WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return IdempotencyCheckResult(state="not_seen", prior_observation=None, error=None)
        observation = None
        try:
            obs_raw = row["observation_json"]
            if obs_raw:
                observation = json.loads(obs_raw)
        except (json.JSONDecodeError, TypeError):
            observation = None
        return IdempotencyCheckResult(
            state=row["state"],
            prior_observation=observation,
            error=row["error"],
        )

    def mark_in_flight(self, idempotency_key: str, invocation_id: str) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        # Immutable succeeded enforcement: WHERE state NOT IN ('succeeded')
        self._db.execute(
            """
            INSERT INTO idempotency_keys (idempotency_key, state, invocation_id, created_at, updated_at)
            VALUES (?, 'in_flight', ?, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                state = 'in_flight',
                invocation_id = excluded.invocation_id,
                updated_at = excluded.updated_at
            WHERE idempotency_keys.state NOT IN ('succeeded')
            """,
            (idempotency_key, invocation_id, now, now),
        )
        self._db.commit()

    def mark_success(self, idempotency_key: str, observation: dict) -> None:
        import json
        import logging
        from datetime import datetime, timezone

        _logger = logging.getLogger(__name__)
        now = datetime.now(timezone.utc).isoformat()
        # Only transition if currently in_flight
        cursor = self._db.execute(
            """
            UPDATE idempotency_keys SET
                state = 'succeeded',
                observation_json = ?,
                updated_at = ?
            WHERE idempotency_key = ? AND state = 'in_flight'
            """,
            (json.dumps(observation, sort_keys=True), now, idempotency_key),
        )
        self._db.commit()
        if cursor.rowcount == 0:
            _logger.warning(
                "mark_success(%s): rowcount=0 — key may not be in_flight or already succeeded",
                idempotency_key,
            )

    def mark_failed(self, idempotency_key: str, error: str) -> None:
        import logging
        from datetime import datetime, timezone

        _logger = logging.getLogger(__name__)
        now = datetime.now(timezone.utc).isoformat()
        # Only transition if currently in_flight
        cursor = self._db.execute(
            """
            UPDATE idempotency_keys SET
                state = 'failed',
                error = ?,
                updated_at = ?
            WHERE idempotency_key = ? AND state = 'in_flight'
            """,
            (error, now, idempotency_key),
        )
        self._db.commit()
        if cursor.rowcount == 0:
            _logger.warning(
                "mark_failed(%s): rowcount=0 — key may not be in_flight or already succeeded",
                idempotency_key,
            )

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        cursor = self._db.execute(
            "DELETE FROM idempotency_keys WHERE updated_at < ? AND state != 'in_flight'",
            (cutoff,),
        )
        self._db.commit()
        return cursor.rowcount
