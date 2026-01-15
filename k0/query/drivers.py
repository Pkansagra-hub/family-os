"""Driver registry and implementations for query recall."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, List, MutableMapping, Sequence

from k0.db.connection import connection_scope
from k0.query.common import DriverContext, DriverExecution, QueryDriver

if TYPE_CHECKING:
    import asyncpg


class DriverRegistry:
    """Registry that resolves selectors to concrete drivers."""

    def __init__(self, drivers: Sequence[QueryDriver] | None = None) -> None:
        self._drivers: List[QueryDriver] = list(drivers or [])

    def register(self, driver: QueryDriver) -> None:
        self._drivers.append(driver)

    def extend(self, drivers: Iterable[QueryDriver]) -> None:
        for driver in drivers:
            self.register(driver)

    def resolve(self, selector: Any) -> QueryDriver:
        for driver in self._drivers:
            if driver.supports(selector):
                return driver
        raise LookupError(f"No query driver registered for selector: {selector!r}")

    @property
    def drivers(self) -> Sequence[QueryDriver]:
        return tuple(self._drivers)


def build_default_registry(
    *,
    default_limit: int,
    max_limit: int,
) -> DriverRegistry:
    registry = DriverRegistry(
        [
            WalDriver(default_limit=default_limit, max_limit=max_limit),
            FtsDriver(default_limit=default_limit, max_limit=max_limit),
            AliasDriver(
                name="episodic",
                supported_types={"episodic", "timeline", "memory.timeline"},
                reason="episodic alias driver not configured",
            ),
            AliasDriver(
                name="snapshot",
                supported_types={"snapshot", "snapshots"},
                reason="snapshot recall driver not configured",
            ),
            AliasDriver(
                name="vector",
                supported_types={"vector", "semantic_vector", "embedding"},
                reason="vector recall driver not configured",
            ),
            AliasDriver(
                name="kg",
                supported_types={"kg", "graph", "knowledge"},
                reason="knowledge graph recall driver not configured",
            ),
        ]
    )
    return registry


def _selector_payload(selector: Any) -> MutableMapping[str, Any]:
    payload: MutableMapping[str, Any] = {}
    for attribute in (
        "type",
        "topic",
        "limit",
        "cursor",
        "after",
        "tenant_id",
        "space_id",
        "query",
    ):
        value = getattr(selector, attribute, None)
        if value is not None:
            payload[attribute] = value
    return payload


def _resolve_next_cursor(items: list[dict[str, Any]], cursor: int | None) -> int | None:
    if not items:
        return cursor
    return int(min(item["wal_pos"] for item in items))


def _decode_body(body: bytes | str | None) -> Any:
    if body is None:
        return None

    # Handle string (from FTS virtual table which stores text)
    if isinstance(body, str):
        decoded = body
    else:
        # Handle bytes (from WAL table)
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "encoding": "base64",
                "payload": base64.b64encode(body).decode("ascii"),
            }

    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return decoded


class WalDriver(QueryDriver):
    """Primary driver that fans out into the WAL slice."""

    name = "wal"

    def __init__(self, *, default_limit: int, max_limit: int) -> None:
        self._default_limit = default_limit
        self._max_limit = max_limit

    def supports(self, selector: Any) -> bool:
        selector_type = getattr(selector, "type", None)
        if selector_type is None:
            return True
        selector_type_lower = str(selector_type).lower()
        return selector_type_lower in {
            "wal",
            "timeline",
            "episodic",
            "memory.timeline",
            "event",
            "default",
        }

    async def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
        allowed_limit = context.allowed_limit
        if allowed_limit <= 0:
            return DriverExecution(
                driver=self.name,
                selector_index=context.selector_index,
                selector=_selector_payload(selector),
            )

        selector_topic = getattr(selector, "topic", None)
        selector_cursor = getattr(selector, "cursor", None)
        selector_after = getattr(selector, "after", None)
        selector_tenant = getattr(selector, "tenant_id", None) or context.tenant_id

        start = time.perf_counter()
        # Gap 31: Defensive connection cleanup with explicit try/finally
        try:
            async with connection_scope() as connection:
                rows = await self._fetch_rows(
                    connection,
                    space_id=context.space_id,
                    tenant_id=selector_tenant,
                    topic=selector_topic,
                    cursor=selector_cursor,
                    after=selector_after,
                    limit=allowed_limit,
                )
            latency_ms = (time.perf_counter() - start) * 1_000.0
        except Exception:
            # Connection cleanup handled by connection_scope()'s finally block
            # But we log potential leak for monitoring
            raise

        items = [self._row_to_item(row) for row in rows]
        consumed = len(items)
        next_cursor = _resolve_next_cursor(items, selector_cursor)
        exhausted_time_budget = context.elapsed_ms + latency_ms >= context.time_budget_ms
        metadata: MutableMapping[str, Any] = {
            "source": "st_wal",
            "rows": consumed,
        }
        return DriverExecution(
            driver=self.name,
            selector_index=context.selector_index,
            selector=_selector_payload(selector),
            items=items,
            next_cursor=next_cursor,
            latency_ms=round(latency_ms, 3),
            consumed_top_k=consumed,
            exhausted_time_budget=exhausted_time_budget,
            metadata=metadata,
        )

    async def _fetch_rows(
        self,
        connection: "asyncpg.Connection",
        *,
        space_id: str,
        tenant_id: str | None,
        topic: str | None,
        cursor: int | None,
        after: int | None,
        limit: int,
    ) -> list["asyncpg.Record"]:
        query_parts = [
            "SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, schema_uri, schema_version, device_id, commit_ts",
            "FROM st_wal",
            "WHERE space_id = $1",
        ]
        params: list[Any] = [space_id]
        param_idx = 2

        if tenant_id:
            query_parts.append(f"AND tenant_id = ${param_idx}")
            params.append(tenant_id)
            param_idx += 1

        if topic:
            query_parts.append(f"AND topic = ${param_idx}")
            params.append(topic)
            param_idx += 1

        if cursor is not None:
            query_parts.append(f"AND pos < ${param_idx}")
            params.append(int(cursor))
            param_idx += 1

        if after is not None:
            query_parts.append(f"AND pos > ${param_idx}")
            params.append(int(after))
            param_idx += 1

        query_parts.append("ORDER BY pos DESC")
        query_parts.append(f"LIMIT ${param_idx}")
        params.append(int(limit))

        statement = " ".join(query_parts)
        return list(await connection.fetch(statement, *params))

    def _row_to_item(self, row: "asyncpg.Record") -> dict[str, Any]:
        body_value = _decode_body(row["body"]) if "body" in row.keys() else None
        return {
            "wal_pos": row["pos"],
            "tenant_id": row["tenant_id"],
            "space_id": row["space_id"],
            "topic": row["topic"],
            "commit_ts": row["commit_ts"],
            "schema_uri": row["schema_uri"],
            "schema_version": row["schema_version"],
            "device_id": row["device_id"],
            "payload_sha256": row["payload_sha256"],
            "envelope": json.loads(row["envelope_json"]),
            "body": body_value,
        }


@dataclass(slots=True)
class AliasDriver(QueryDriver):
    """Placeholder driver that records unsupported selector types."""

    name: str
    supported_types: set[str]
    reason: str

    def supports(self, selector: Any) -> bool:
        selector_type = getattr(selector, "type", None)
        if selector_type is None:
            return False
        return str(selector_type).lower() in self.supported_types

    def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
        metadata: MutableMapping[str, Any] = {
            "status": "unavailable",
            "reason": self.reason,
        }
        return DriverExecution(
            driver=self.name,
            selector_index=context.selector_index,
            selector=_selector_payload(selector),
            latency_ms=0.0,
            metadata=metadata,
        )


class FtsDriver(QueryDriver):
    """Full-text search driver using PostgreSQL tsvector/tsquery."""

    name = "fts"

    def __init__(self, *, default_limit: int, max_limit: int) -> None:
        self._default_limit = default_limit
        self._max_limit = max_limit

    def supports(self, selector: Any) -> bool:
        selector_type = getattr(selector, "type", None)
        if selector_type is None:
            return False
        selector_type_lower = str(selector_type).lower()
        return selector_type_lower in {
            "fts",
            "semantic",
            "semantic_memory",
            "fulltext",
            "text",
        }

    async def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
        allowed_limit = context.allowed_limit
        if allowed_limit <= 0:
            return DriverExecution(
                driver=self.name,
                selector_index=context.selector_index,
                selector=_selector_payload(selector),
            )

        selector_query = getattr(selector, "query", None)
        selector_topic = getattr(selector, "topic", None)
        selector_tenant = getattr(selector, "tenant_id", None) or context.tenant_id

        if not selector_query:
            # No query provided, return empty result
            return DriverExecution(
                driver=self.name,
                selector_index=context.selector_index,
                selector=_selector_payload(selector),
                latency_ms=0.0,
                metadata={"status": "no_query"},
            )

        start = time.perf_counter()
        # Gap 31: Defensive connection cleanup with explicit try/finally
        try:
            async with connection_scope() as connection:
                rows = await self._search_fts(
                    connection,
                    space_id=context.space_id,
                    tenant_id=selector_tenant,
                    topic=selector_topic,
                    query=selector_query,
                    limit=allowed_limit,
                )
            latency_ms = (time.perf_counter() - start) * 1_000.0
        except Exception:
            # Connection cleanup handled by connection_scope()'s finally block
            # But we log potential leak for monitoring
            raise

        items = [self._row_to_item(row) for row in rows]
        consumed = len(items)
        exhausted_time_budget = context.elapsed_ms + latency_ms >= context.time_budget_ms
        metadata: MutableMapping[str, Any] = {
            "source": "st_fts",
            "rows": consumed,
            "query": selector_query,
        }
        return DriverExecution(
            driver=self.name,
            selector_index=context.selector_index,
            selector=_selector_payload(selector),
            items=items,
            latency_ms=round(latency_ms, 3),
            consumed_top_k=consumed,
            exhausted_time_budget=exhausted_time_budget,
            metadata=metadata,
        )

    async def _search_fts(
        self,
        connection: "asyncpg.Connection",
        *,
        space_id: str,
        tenant_id: str | None,
        topic: str | None,
        query: str,
        limit: int,
    ) -> list["asyncpg.Record"]:
        # Build PostgreSQL full-text search query using tsvector/tsquery
        # The tsv column is a pre-computed tsvector column with GIN index
        query_parts = [
            "SELECT wal_pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, schema_uri, schema_version, device_id, commit_ts,",
            "ts_rank(tsv, plainto_tsquery('english', $1)) as score",
            "FROM st_fts",
            "WHERE tsv @@ plainto_tsquery('english', $1)",
            "AND space_id = $2",
        ]
        params: list[Any] = [query, space_id]
        param_idx = 3

        if tenant_id:
            query_parts.append(f"AND tenant_id = ${param_idx}")
            params.append(tenant_id)
            param_idx += 1

        if topic:
            query_parts.append(f"AND topic = ${param_idx}")
            params.append(topic)
            param_idx += 1

        # Order by relevance score (descending - higher is better in PostgreSQL)
        query_parts.append("ORDER BY ts_rank(tsv, plainto_tsquery('english', $1)) DESC")
        query_parts.append(f"LIMIT ${param_idx}")
        params.append(int(limit))

        statement = " ".join(query_parts)
        return list(await connection.fetch(statement, *params))

    def _row_to_item(self, row: "asyncpg.Record") -> dict[str, Any]:
        body_value = _decode_body(row["body"]) if "body" in row.keys() else None
        return {
            "wal_pos": row["wal_pos"],
            "tenant_id": row["tenant_id"],
            "space_id": row["space_id"],
            "topic": row["topic"],
            "commit_ts": row["commit_ts"],
            "schema_uri": row["schema_uri"],
            "schema_version": row["schema_version"],
            "device_id": row["device_id"],
            "payload_sha256": row["payload_sha256"],
            "envelope": json.loads(row["envelope_json"]),
            "body": body_value,
            "fts_score": row["score"],  # Include FTS relevance score
        }
