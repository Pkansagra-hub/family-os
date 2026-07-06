"""LocalProjectionStore — per-session store for connected resources, household members, aliases.

Phase 1, Epic 1 (Issue 1.5).  Per whiteboard Component 2.
Each session gets its own instance (typically ``:memory:``).

.. note::
    ``space_id`` is accepted by ``rebuild_alias_index`` for contract
    compatibility but is unused because the store is per-session —
    every row already belongs to one session.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalProjectionStore:
    """Per-session SQLite store for household-local projection data."""

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
            raise RuntimeError("LocalProjectionStore is not open")
        return self._conn

    # ── Schema ─────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        db = self._db
        db.execute("""
            CREATE TABLE IF NOT EXISTS connected_resources (
                resource_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                resource_kind TEXT NOT NULL,
                connector_id TEXT NOT NULL DEFAULT '',
                backend_id TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                permissions TEXT NOT NULL DEFAULT 'read_write'
                    CHECK(permissions IN ('read_write','read_only','restricted','none')),
                freshness_state TEXT NOT NULL DEFAULT 'fresh'
                    CHECK(freshness_state IN ('fresh','stale','unknown')),
                last_synced_at TEXT NOT NULL DEFAULT ''
            )
            """)
        # Backward-compat: add columns if upgrading from schema without backend_id/session_id
        for col, col_type in [
            ("backend_id", "TEXT NOT NULL DEFAULT ''"),
            ("session_id", "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                db.execute(f"ALTER TABLE connected_resources ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # column already exists
        db.execute("""
            CREATE TABLE IF NOT EXISTS household_members (
                person_id TEXT PRIMARY KEY,
                label TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'member',
                linked_resource_ids_json TEXT NOT NULL DEFAULT '{}'
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS alias_index (
                alias TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                PRIMARY KEY(alias, entity_id, actor_id)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS resource_projection_snapshots (
                resource_id TEXT PRIMARY KEY,
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                captured_at TEXT NOT NULL DEFAULT ''
            )
            """)

    # ── Connected Resources ────────────────────────────────────────────

    def upsert_connected_resource(self, resource: dict) -> None:

        self._db.execute(
            """
            INSERT INTO connected_resources (resource_id, actor_id, resource_kind,
                connector_id, backend_id, session_id, label, status, permissions,
                freshness_state, last_synced_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(resource_id) DO UPDATE SET
                actor_id=excluded.actor_id, resource_kind=excluded.resource_kind,
                connector_id=excluded.connector_id,
                backend_id=excluded.backend_id,
                session_id=excluded.session_id,
                label=excluded.label,
                status=excluded.status, permissions=excluded.permissions,
                freshness_state=excluded.freshness_state,
                last_synced_at=excluded.last_synced_at
            """,
            (
                resource.get("resource_id", ""),
                resource.get("actor_id", ""),
                resource.get("resource_kind", ""),
                resource.get("connector_id", ""),
                resource.get("backend_id", ""),
                resource.get("session_id", ""),
                resource.get("label", ""),
                resource.get("status", "active"),
                resource.get("permissions", "read_write"),
                resource.get("freshness_state", "fresh"),
                resource.get("last_synced_at", ""),
            ),
        )
        self._db.commit()

    def get_connected_resource(self, resource_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM connected_resources WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_connected_resources(
        self,
        actor_id: str,
        *,
        resource_kind: str | None = None,
        status: str = "active",
    ) -> list[dict]:
        if resource_kind is not None:
            rows = self._db.execute(
                """
                SELECT * FROM connected_resources
                WHERE actor_id = ? AND status = ? AND resource_kind = ?
                """,
                (actor_id, status, resource_kind),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT * FROM connected_resources
                WHERE actor_id = ? AND status = ?
                """,
                (actor_id, status),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── RES-011c: Session-aware backends (2026-06-17) ──────────────────

    def get_connected_backends(
        self,
        session_id: str,
        connector_id: str,
    ) -> list[dict]:
        """Return backends connected for this session + connector.

        Returns list of {backend_id, label, status}.
        Used by RES-011b to populate dynamic enums on tool schemas.
        Read-only — the write path is owned by the native FamilyOS app
        inbound API, NOT the resolver.
        """
        rows = self._db.execute(
            """
            SELECT DISTINCT backend_id, label, status
            FROM connected_resources
            WHERE session_id = ? AND connector_id = ? AND status = 'active'
            """,
            (session_id, connector_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Household Members ──────────────────────────────────────────────

    def upsert_household_member(self, member: dict) -> None:
        self._db.execute(
            """
            INSERT INTO household_members (person_id, label, role, linked_resource_ids_json)
            VALUES (?,?,?,?)
            ON CONFLICT(person_id) DO UPDATE SET
                label=excluded.label, role=excluded.role,
                linked_resource_ids_json=excluded.linked_resource_ids_json
            """,
            (
                member.get("person_id", ""),
                member.get("label", ""),
                member.get("role", "member"),
                json.dumps(member.get("linked_resource_ids", {}), sort_keys=True),
            ),
        )
        self._db.commit()

    def get_household_member(self, person_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM household_members WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        if row is None:
            return None

        d = dict(row)
        d["linked_resource_ids"] = json.loads(d.pop("linked_resource_ids_json", "{}"))
        return d

    # ── Alias Index ────────────────────────────────────────────────────

    def resolve_alias(
        self,
        alias: str,
        actor_id: str,
        *,
        entity_type: str | None = None,
    ) -> list[dict]:
        if entity_type is not None:
            rows = self._db.execute(
                """
                SELECT alias, entity_id, entity_type, actor_id
                FROM alias_index
                WHERE alias = ? AND actor_id = ? AND entity_type = ?
                """,
                (alias, actor_id, entity_type),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT alias, entity_id, entity_type, actor_id
                FROM alias_index
                WHERE alias = ? AND actor_id = ?
                """,
                (alias, actor_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def fuzzy_resolve_alias(
        self,
        alias: str,
        actor_id: str,
        *,
        entity_type: str | None = None,
    ) -> list[dict]:
        # LIKE-based fuzzy match
        pattern = f"%{alias}%"
        if entity_type is not None:
            rows = self._db.execute(
                """
                SELECT alias, entity_id, entity_type, actor_id
                FROM alias_index
                WHERE alias LIKE ? AND actor_id = ? AND entity_type = ?
                """,
                (pattern, actor_id, entity_type),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT alias, entity_id, entity_type, actor_id
                FROM alias_index
                WHERE alias LIKE ? AND actor_id = ?
                """,
                (pattern, actor_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_alias_index(
        self,
        actor_id: str,
        alias: str,
        entity_id: str,
        entity_type: str,
    ) -> None:
        """Insert or update a single alias entry.

        Useful for test seeding and runtime alias registration.
        """
        self._db.execute(
            """
            INSERT OR REPLACE INTO alias_index (alias, entity_id, entity_type, actor_id)
            VALUES (?,?,?,?)
            """,
            (alias, entity_id, entity_type, actor_id),
        )
        self._db.commit()

    def rebuild_alias_index(self, actor_id: str, space_id: str) -> None:
        """Rebuild alias entries from connected_resources and household_members.

        ``space_id`` is accepted for contract compatibility but is unused
        because this store is per-session — every row already belongs to
        one session.
        """
        # Delete existing aliases for this actor before rebuilding
        self._db.execute("DELETE FROM alias_index WHERE actor_id = ?", (actor_id,))

        # Index connected resources by label
        resources = self._db.execute(
            "SELECT resource_id, label, resource_kind, connector_id FROM connected_resources WHERE actor_id = ? AND status = 'active'",
            (actor_id,),
        ).fetchall()
        for r in resources:
            label = r["label"].strip().lower()
            if label:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO alias_index (alias, entity_id, entity_type, actor_id)
                    VALUES (?,?,?,?)
                    """,
                    (label, r["resource_id"], "resource", actor_id),
                )
            kind = r["resource_kind"].strip().lower()
            if kind:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO alias_index (alias, entity_id, entity_type, actor_id)
                    VALUES (?,?,?,?)
                    """,
                    (kind, r["resource_id"], "resource", actor_id),
                )

        # Index household members by label
        members = self._db.execute(
            "SELECT person_id, label, role FROM household_members"
        ).fetchall()
        for m in members:
            label = m["label"].strip().lower()
            if label:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO alias_index (alias, entity_id, entity_type, actor_id)
                    VALUES (?,?,?,?)
                    """,
                    (label, m["person_id"], "person", actor_id),
                )
        self._db.commit()

    # ── Projection Snapshots ───────────────────────────────────────────

    def upsert_projection_snapshot(self, snapshot: dict) -> None:
        self._db.execute(
            """
            INSERT INTO resource_projection_snapshots (resource_id, snapshot_json, captured_at)
            VALUES (?,?,?)
            ON CONFLICT(resource_id) DO UPDATE SET
                snapshot_json=excluded.snapshot_json,
                captured_at=excluded.captured_at
            """,
            (
                snapshot.get("resource_id", ""),
                json.dumps(snapshot.get("snapshot", {}), sort_keys=True),
                snapshot.get("captured_at", ""),
            ),
        )
        self._db.commit()

    def get_fresh_snapshot(self, resource_id: str, max_age_seconds: int = 300) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM resource_projection_snapshots WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()
        if row is None:
            return None
        captured = row["captured_at"]
        if captured:
            try:
                # Handle both naive and timezone-aware ISO timestamps.
                # If the stored timestamp has no timezone offset, treat
                # it as UTC (the standard for all FamilyOS timestamps).
                captured_dt = datetime.fromisoformat(captured)
                if captured_dt.tzinfo is None:
                    captured_dt = captured_dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - captured_dt).total_seconds()
                if age > max_age_seconds:
                    return None  # stale
            except (ValueError, TypeError):
                pass
        d = dict(row)
        d["snapshot"] = json.loads(d.pop("snapshot_json", "{}"))
        return d

    # ── Freshness ──────────────────────────────────────────────────────

    def mark_resource_stale(self, resource_id: str) -> None:
        self._db.execute(
            "UPDATE connected_resources SET freshness_state = 'stale' WHERE resource_id = ?",
            (resource_id,),
        )
        self._db.commit()

    def mark_resource_fresh(self, resource_id: str) -> None:
        self._db.execute(
            "UPDATE connected_resources SET freshness_state = 'fresh' WHERE resource_id = ?",
            (resource_id,),
        )
        self._db.commit()

    def reset(self) -> None:
        """Drop all data — used between tests."""
        self._db.execute("DELETE FROM connected_resources")
        self._db.execute("DELETE FROM household_members")
        self._db.execute("DELETE FROM alias_index")
        self._db.execute("DELETE FROM resource_projection_snapshots")
        self._db.commit()
