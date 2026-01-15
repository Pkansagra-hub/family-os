"""Schema registry access layer used by the Minimal Gate - Async PostgreSQL."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator, Dict, Iterable, Sequence

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg

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


@asynccontextmanager
async def _resolve_connection(
    connection: "asyncpg.Connection | None",
) -> AsyncIterator["asyncpg.Connection"]:
    if connection is not None:
        yield connection
        return

    async with connection_scope() as pooled_connection:
        yield pooled_connection


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
    """Cached facade backed by the schema_registry PostgreSQL table."""

    def __init__(self, metrics_exporter=None) -> None:
        self._cache: Dict[tuple[str, str], SchemaRecord] = {}
        self._lock = asyncio.Lock()
        self._loaded = False
        self._metrics_exporter = metrics_exporter

    async def clear_cache(self) -> None:
        async with self._lock:
            self._cache.clear()
            self._loaded = False
            if self._metrics_exporter is not None:
                self._metrics_exporter.set_gauge("schema_cache_entries_active", 0.0)

    async def load(self, *, connection: "asyncpg.Connection | None" = None) -> None:
        """Load schema metadata into the process cache."""

        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry"
            )
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
        async with self._lock:
            self._cache = records
            self._loaded = True
            if self._metrics_exporter is not None:
                self._metrics_exporter.set_gauge(
                    "schema_cache_entries_active", float(len(self._cache))
                )

    async def get(
        self,
        uri: str,
        version: str,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> SchemaRecord:
        key = (uri, version)
        async with self._lock:
            record = self._cache.get(key)
            if record is not None:
                if self._metrics_exporter is not None:
                    self._metrics_exporter.emit("schema_cache_hits_total")
                return record

        if self._metrics_exporter is not None:
            self._metrics_exporter.emit("schema_cache_misses_total")

        async with _resolve_connection(connection) as conn:
            row = await conn.fetchrow(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry WHERE schema_uri=$1 AND version=$2",
                uri,
                version,
            )

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

        async with self._lock:
            self._cache[key] = record
            if self._metrics_exporter is not None:
                self._metrics_exporter.set_gauge(
                    "schema_cache_entries_active", float(len(self._cache))
                )
        return record

    async def register(
        self,
        record: SchemaRecord,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> SchemaRecord:
        import asyncpg as asyncpg_module

        stored_record = self._normalize_record(record)
        async with _resolve_connection(connection) as conn:
            try:
                await conn.execute(
                    "INSERT INTO schema_registry (schema_uri, version, sha256, status) VALUES ($1, $2, $3, $4)",
                    stored_record.uri,
                    stored_record.version,
                    stored_record.sha256,
                    stored_record.status,
                )
            except asyncpg_module.UniqueViolationError as exc:
                msg = f"Schema {stored_record.uri}@{stored_record.version} already exists"
                raise ValueError(msg) from exc
        await self._store(stored_record)
        return stored_record

    async def upsert(
        self,
        record: SchemaRecord,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> SchemaRecord:
        stored_record = self._normalize_record(record)
        async with _resolve_connection(connection) as conn:
            await conn.execute(
                """
                INSERT INTO schema_registry (schema_uri, version, sha256, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT(schema_uri, version) DO UPDATE SET
                    sha256 = EXCLUDED.sha256,
                    status = EXCLUDED.status
                """,
                stored_record.uri,
                stored_record.version,
                stored_record.sha256,
                stored_record.status,
            )
        await self._store(stored_record)
        return stored_record

    async def promote(
        self,
        uri: str,
        version: str,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> SchemaRecord:
        from datetime import datetime, timezone

        unblocked_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        async with _resolve_connection(connection) as conn:
            row = await conn.fetchrow(
                "SELECT schema_uri, version, sha256, status FROM schema_registry WHERE schema_uri=$1 AND version=$2",
                uri,
                version,
            )
            if row is None:
                msg = f"Schema {uri}@{version} not found"
                raise KeyError(msg)

            # Demote other versions to maintain N/N+1 policy
            await conn.execute(
                "UPDATE schema_registry SET status='BLOCKED' WHERE schema_uri=$1 AND status='DEPRECATED' AND version != $2",
                uri,
                version,
            )
            await conn.execute(
                "UPDATE schema_registry SET status='DEPRECATED' WHERE schema_uri=$1 AND status='ACTIVE' AND version != $2",
                uri,
                version,
            )
            # Set unblocked_ts if this version was previously blocked
            await conn.execute(
                """
                UPDATE schema_registry
                SET status='ACTIVE', unblocked_ts=$1
                WHERE schema_uri=$2 AND version=$3 AND operator_id IS NOT NULL
                """,
                unblocked_ts,
                uri,
                version,
            )
            # For versions never blocked, just set ACTIVE
            await conn.execute(
                """
                UPDATE schema_registry
                SET status='ACTIVE'
                WHERE schema_uri=$1 AND version=$2 AND operator_id IS NULL
                """,
                uri,
                version,
            )
            rows = await conn.fetch(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry WHERE schema_uri=$1",
                uri,
            )

        await self._refresh_uri_cache(uri, rows)
        return self._cache[(uri, version)]

    async def block(
        self,
        uri: str,
        version: str,
        *,
        operator_id: str,
        reason: str,
        connection: "asyncpg.Connection | None" = None,
    ) -> SchemaRecord:
        """Block a schema version with full audit trail."""
        if not operator_id or not operator_id.strip():
            msg = "operator_id is required for block operations"
            raise ValueError(msg)
        if not reason or not reason.strip():
            msg = "reason is required for block operations"
            raise ValueError(msg)

        from datetime import datetime, timezone

        blocked_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        async with _resolve_connection(connection) as conn:
            result = await conn.execute(
                """
                UPDATE schema_registry
                SET
                  status='BLOCKED',
                  operator_id=$1,
                  blocked_ts=$2,
                  blocked_reason=$3,
                  unblocked_ts=NULL
                WHERE schema_uri=$4 AND version=$5
                """,
                operator_id,
                blocked_ts,
                reason,
                uri,
                version,
            )
            # Check if update affected any rows
            if result == "UPDATE 0":
                msg = f"Schema {uri}@{version} not found"
                raise KeyError(msg)
            rows = await conn.fetch(
                "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry WHERE schema_uri=$1",
                uri,
            )

        await self._refresh_uri_cache(uri, rows)
        return self._cache[(uri, version)]

    def active_versions(self, uri: str) -> Iterable[SchemaRecord]:
        # Note: This is sync for cache access only
        return tuple(
            record
            for (record_uri, _), record in self._cache.items()
            if record_uri == uri and record.status == "ACTIVE"
        )

    def records_for_uri(self, uri: str) -> Iterable[SchemaRecord]:
        # Note: This is sync for cache access only
        return tuple(record for (record_uri, _), record in self._cache.items() if record_uri == uri)

    async def get_audit_trail(
        self,
        uri: str | None = None,
        version: str | None = None,
        status: str | None = None,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> Iterable[SchemaRecord]:
        """Query schema registry with optional filters for audit trail reporting."""
        query_parts = [
            "SELECT schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts FROM schema_registry"
        ]
        params: list[str] = []
        where_clauses: list[str] = []
        param_idx = 1

        if uri is not None:
            where_clauses.append(f"schema_uri=${param_idx}")
            params.append(uri)
            param_idx += 1
        if version is not None:
            if uri is None:
                msg = "version filter requires uri parameter"
                raise ValueError(msg)
            where_clauses.append(f"version=${param_idx}")
            params.append(version)
            param_idx += 1
        if status is not None:
            where_clauses.append(f"status=${param_idx}")
            params.append(status.upper())
            param_idx += 1

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        query = " ".join(query_parts)

        async with _resolve_connection(connection) as conn:
            rows = await conn.fetch(query, *params)

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

    async def _store(self, record: SchemaRecord) -> None:
        async with self._lock:
            self._cache[(record.uri, record.version)] = record
            self._loaded = True

    async def _refresh_uri_cache(self, uri: str, rows) -> None:
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
        async with self._lock:
            keys_to_remove = [key for key in self._cache if key[0] == uri]
            for key in keys_to_remove:
                del self._cache[key]
            self._cache.update(records)
            self._loaded = True
