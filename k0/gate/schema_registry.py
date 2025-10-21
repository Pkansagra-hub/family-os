"""Schema registry access layer used by the Minimal Gate."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, Sequence

from k0.uow.connection_pool import connection_scope

ALLOWED_STATUSES: Sequence[str] = (
    "REGISTERED",
    "ACTIVE",
    "DEPRECATED",
    "BLOCKED",
)


@dataclass(slots=True)
class SchemaRecord:
    uri: str
    version: str
    sha256: str
    status: str
    # Audit trail fields (ADR 002: nullable for backward compatibility)
    operator_id: str | None = None
    blocked_ts: str | None = None
    blocked_reason: str | None = None
    unblocked_ts: str | None = None


@contextmanager
def _resolve_connection(
    connection: sqlite3.Connection | None,
) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
        return

    with connection_scope() as pooled_connection:
        yield pooled_connection
        pooled_connection.commit()


def _ensure_row_factory(connection: sqlite3.Connection) -> None:
    if connection.row_factory is None:
        connection.row_factory = sqlite3.Row


def _normalize_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        msg = "sha256 must be a 64-character hexadecimal digest"
        raise ValueError(msg)
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError("sha256 must be a hexadecimal digest") from exc
    return normalized


class SchemaRegistry:
    """Cached facade backed by the schema_registry SQLite table."""

    def __init__(self) -> None:
        self._cache: Dict[tuple[str, str], SchemaRecord] = {}
        self._lock = threading.RLock()
        self._loaded = False

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._loaded = False

    def load(self, *, connection: sqlite3.Connection | None = None) -> None:
        """Load schema metadata into the process cache."""

        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            rows = conn.execute(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry"
            ).fetchall()
        records = {
            (row["schema_uri"], row["version"]): SchemaRecord(
                uri=row["schema_uri"],
                version=row["version"],
                sha256=row["sha256"],
                status=row["status"].upper(),
                operator_id=row["operator_id"],
                blocked_ts=row["blocked_ts"],
                blocked_reason=row["blocked_reason"],
                unblocked_ts=row["unblocked_ts"],
            )
            for row in rows
        }
        with self._lock:
            self._cache = records
            self._loaded = True

    def get(
        self,
        uri: str,
        version: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> SchemaRecord:
        key = (uri, version)
        with self._lock:
            record = self._cache.get(key)
            if record is not None:
                return record

        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            row = conn.execute(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry WHERE schema_uri=? AND version=?",
                (uri, version),
            ).fetchone()

        if row is None:
            msg = f"Schema {uri}@{version} not found"
            raise KeyError(msg)

        record = SchemaRecord(
            uri=row["schema_uri"],
            version=row["version"],
            sha256=row["sha256"],
            status=row["status"].upper(),
            operator_id=row["operator_id"],
            blocked_ts=row["blocked_ts"],
            blocked_reason=row["blocked_reason"],
            unblocked_ts=row["unblocked_ts"],
        )

        with self._lock:
            self._cache[key] = record
        return record

    def register(
        self,
        record: SchemaRecord,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> SchemaRecord:
        stored_record = self._normalize_record(record)
        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            try:
                conn.execute(
                    (
                        "INSERT INTO schema_registry (schema_uri, version, sha256, status) VALUES (?, ?, ?, ?)"
                    ),
                    (
                        stored_record.uri,
                        stored_record.version,
                        stored_record.sha256,
                        stored_record.status,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                msg = (
                    f"Schema {stored_record.uri}@{stored_record.version} already exists"
                )
                raise ValueError(msg) from exc
        self._store(stored_record)
        return stored_record

    def upsert(
        self,
        record: SchemaRecord,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> SchemaRecord:
        stored_record = self._normalize_record(record)
        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            conn.execute(
                (
                    "INSERT INTO schema_registry (schema_uri, version, sha256, status) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(schema_uri, version) DO UPDATE SET sha256=excluded.sha256, status=excluded.status"
                ),
                (
                    stored_record.uri,
                    stored_record.version,
                    stored_record.sha256,
                    stored_record.status,
                ),
            )
        self._store(stored_record)
        return stored_record

    def promote(
        self,
        uri: str,
        version: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> SchemaRecord:
        from datetime import datetime, timezone

        unblocked_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            row = conn.execute(
                "SELECT schema_uri, version, sha256, status FROM schema_registry WHERE schema_uri=? AND version=?",
                (uri, version),
            ).fetchone()
            if row is None:
                msg = f"Schema {uri}@{version} not found"
                raise KeyError(msg)

            # Note: BLOCKED schemas CAN be promoted (unblock workflow)
            # Demote other versions to maintain N/N+1 policy
            conn.execute(
                "UPDATE schema_registry SET status='BLOCKED' WHERE schema_uri=? AND status='DEPRECATED' AND version != ?",
                (uri, version),
            )
            conn.execute(
                "UPDATE schema_registry SET status='DEPRECATED' WHERE schema_uri=? AND status='ACTIVE' AND version != ?",
                (uri, version),
            )
            # Set unblocked_ts if this version was previously blocked (has operator_id)
            conn.execute(
                """
                UPDATE schema_registry
                SET status='ACTIVE', unblocked_ts=?
                WHERE schema_uri=? AND version=? AND operator_id IS NOT NULL
                """,
                (unblocked_ts, uri, version),
            )
            # For versions never blocked, just set ACTIVE
            conn.execute(
                """
                UPDATE schema_registry
                SET status='ACTIVE'
                WHERE schema_uri=? AND version=? AND operator_id IS NULL
                """,
                (uri, version),
            )
            rows = conn.execute(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry WHERE schema_uri=?",
                (uri,),
            ).fetchall()

        self._refresh_uri_cache(uri, rows)
        return self._cache[(uri, version)]

    def block(
        self,
        uri: str,
        version: str,
        *,
        operator_id: str,
        reason: str,
        connection: sqlite3.Connection | None = None,
    ) -> SchemaRecord:
        """Block a schema version with full audit trail.

        Args:
            uri: Schema URI to block
            version: Version to block
            operator_id: Email/ID of operator performing block (required)
            reason: Justification for emergency block (required)
            connection: Optional DB connection

        Returns:
            Updated SchemaRecord with audit metadata

        Raises:
            ValueError: If operator_id or reason is empty
            KeyError: If schema version not found
        """
        if not operator_id or not operator_id.strip():
            msg = "operator_id is required for block operations"
            raise ValueError(msg)
        if not reason or not reason.strip():
            msg = "reason is required for block operations"
            raise ValueError(msg)

        from datetime import datetime, timezone

        blocked_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            updated = conn.execute(
                """
                UPDATE schema_registry
                SET
                  status='BLOCKED',
                  operator_id=?,
                  blocked_ts=?,
                  blocked_reason=?,
                  unblocked_ts=NULL
                WHERE schema_uri=? AND version=?
                """,
                (operator_id, blocked_ts, reason, uri, version),
            )
            if updated.rowcount == 0:
                msg = f"Schema {uri}@{version} not found"
                raise KeyError(msg)
            rows = conn.execute(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry WHERE schema_uri=?",
                (uri,),
            ).fetchall()

        self._refresh_uri_cache(uri, rows)
        return self._cache[(uri, version)]

    def active_versions(self, uri: str) -> Iterable[SchemaRecord]:
        with self._lock:
            return tuple(
                record
                for (record_uri, _), record in self._cache.items()
                if record_uri == uri and record.status == "ACTIVE"
            )

    def records_for_uri(self, uri: str) -> Iterable[SchemaRecord]:
        with self._lock:
            return tuple(
                record
                for (record_uri, _), record in self._cache.items()
                if record_uri == uri
            )

    def get_audit_trail(
        self,
        uri: str | None = None,
        version: str | None = None,
        status: str | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Iterable[SchemaRecord]:
        """Query schema registry with optional filters for audit trail reporting.

        Args:
            uri: Filter by schema URI (optional)
            version: Filter by version (optional, requires uri)
            status: Filter by status (optional)
            connection: Optional DB connection

        Returns:
            Iterable of SchemaRecord instances with audit metadata
        """
        query_parts = [
            "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry"
        ]
        params: list[str] = []
        where_clauses: list[str] = []

        if uri is not None:
            where_clauses.append("schema_uri=?")
            params.append(uri)
        if version is not None:
            if uri is None:
                msg = "version filter requires uri parameter"
                raise ValueError(msg)
            where_clauses.append("version=?")
            params.append(version)
        if status is not None:
            where_clauses.append("status=?")
            params.append(status.upper())

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        query = " ".join(query_parts)

        with _resolve_connection(connection) as conn:
            _ensure_row_factory(conn)
            rows = conn.execute(query, tuple(params)).fetchall()

        return tuple(
            SchemaRecord(
                uri=row["schema_uri"],
                version=row["version"],
                sha256=row["sha256"],
                status=row["status"].upper(),
                operator_id=row["operator_id"],
                blocked_ts=row["blocked_ts"],
                blocked_reason=row["blocked_reason"],
                unblocked_ts=row["unblocked_ts"],
            )
            for row in rows
        )

    def _normalize_record(self, record: SchemaRecord) -> SchemaRecord:
        uri = record.uri.strip()
        version = record.version.strip()
        sha256 = _normalize_sha256(record.sha256)
        status = record.status.strip().upper()

        if not uri:
            raise ValueError("schema_uri must not be empty")
        if not version:
            raise ValueError("version must not be empty")
        if status not in ALLOWED_STATUSES:
            allowed = ", ".join(ALLOWED_STATUSES)
            raise ValueError(f"status must be one of: {allowed}")

        return SchemaRecord(uri=uri, version=version, sha256=sha256, status=status)

    def _store(self, record: SchemaRecord) -> None:
        with self._lock:
            self._cache[(record.uri, record.version)] = record
            self._loaded = True

    def _refresh_uri_cache(self, uri: str, rows: Sequence[sqlite3.Row]) -> None:
        records = {
            (row["schema_uri"], row["version"]): SchemaRecord(
                uri=row["schema_uri"],
                version=row["version"],
                sha256=row["sha256"],
                status=row["status"].upper(),
                operator_id=row["operator_id"],
                blocked_ts=row["blocked_ts"],
                blocked_reason=row["blocked_reason"],
                unblocked_ts=row["unblocked_ts"],
            )
            for row in rows
        }
        with self._lock:
            keys_to_remove = [key for key in self._cache if key[0] == uri]
            for key in keys_to_remove:
                del self._cache[key]
            self._cache.update(records)
            self._loaded = True
