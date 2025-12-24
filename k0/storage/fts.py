"""FTS (Full Text Search) storage operations - Async PostgreSQL with tsvector."""

from __future__ import annotations

import json
import logging
from typing import Any

from k0.db.connection import connection_scope

LOGGER = logging.getLogger(__name__)


class FtsStore:
    """Storage operations for FTS using PostgreSQL tsvector/GIN."""

    def __init__(self) -> None:
        pass

    async def index_wal_entry(
        self,
        *,
        wal_pos: int,
        tenant_id: str,
        space_id: str,
        topic: str,
        envelope_json: str,
        body: bytes | None,
        payload_sha256: str | None,
        schema_uri: str,
        schema_version: str,
        device_id: str,
        commit_ts: str,
    ) -> None:
        """Index a WAL entry in the FTS table for full-text search.

        Extracts searchable text content from envelope and body.
        """
        # Extract searchable content
        content_parts = []

        # Add envelope fields that might be searchable
        try:
            envelope = json.loads(envelope_json)
            for key, value in envelope.items():
                if isinstance(value, str) and len(value.strip()) > 0:
                    content_parts.append(f"{key}:{value}")
        except (json.JSONDecodeError, TypeError):
            pass

        # Add body content if it's text
        if body:
            try:
                body_text = body.decode("utf-8")
                content_parts.append(body_text)
            except (UnicodeDecodeError, AttributeError):
                # Binary data, skip
                pass

        content = " ".join(content_parts)

        if not content.strip():
            # No searchable content, skip indexing
            return

        async with connection_scope() as connection:
            await connection.execute(
                """
                INSERT INTO st_fts (
                    wal_pos, tenant_id, space_id, topic, content,
                    envelope_json, body, payload_sha256, schema_uri,
                    schema_version, device_id, commit_ts
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (wal_pos) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    space_id = EXCLUDED.space_id,
                    topic = EXCLUDED.topic,
                    content = EXCLUDED.content,
                    envelope_json = EXCLUDED.envelope_json,
                    body = EXCLUDED.body,
                    payload_sha256 = EXCLUDED.payload_sha256,
                    schema_uri = EXCLUDED.schema_uri,
                    schema_version = EXCLUDED.schema_version,
                    device_id = EXCLUDED.device_id,
                    commit_ts = EXCLUDED.commit_ts
                """,
                wal_pos,
                tenant_id,
                space_id,
                topic,
                content,
                envelope_json,
                body,
                payload_sha256,
                schema_uri,
                schema_version,
                device_id,
                commit_ts,
            )

    async def remove_wal_entry(self, *, wal_pos: int) -> None:
        """Remove a WAL entry from the FTS index."""
        async with connection_scope() as connection:
            await connection.execute("DELETE FROM st_fts WHERE wal_pos = $1", wal_pos)

    async def search(
        self,
        *,
        query: str,
        space_id: str,
        tenant_id: str | None = None,
        topic: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search the FTS index and return matching entries.

        Uses PostgreSQL ts_rank for scoring instead of SQLite bm25.
        """
        async with connection_scope() as connection:
            # Build dynamic query with PostgreSQL full-text search
            params: list[Any] = [query, space_id]
            param_idx = 3

            query_parts = [
                """
                SELECT wal_pos, tenant_id, space_id, topic, envelope_json, body,
                       payload_sha256, schema_uri, schema_version, device_id, commit_ts,
                       ts_rank(to_tsvector('english', content), plainto_tsquery('english', $1)) as score
                FROM st_fts
                WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
                AND space_id = $2
                """
            ]

            if tenant_id:
                query_parts.append(f"AND tenant_id = ${param_idx}")
                params.append(tenant_id)
                param_idx += 1

            if topic:
                query_parts.append(f"AND topic = ${param_idx}")
                params.append(topic)
                param_idx += 1

            query_parts.append(f"ORDER BY score DESC LIMIT ${param_idx}")
            params.append(limit)

            statement = " ".join(query_parts)
            rows = await connection.fetch(statement, *params)

            results = []
            for row in rows:
                body_value = None
                if row["body"]:
                    try:
                        body_value = row["body"].decode("utf-8")
                    except UnicodeDecodeError:
                        body_value = {
                            "encoding": "base64",
                            "payload": __import__("base64").b64encode(row["body"]).decode("ascii"),
                        }

                results.append(
                    {
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
                        "fts_score": row["score"],
                    }
                )

            return results

    async def get_stats(self) -> dict[str, Any]:
        """Get FTS table statistics."""
        async with connection_scope() as connection:
            total_docs = await connection.fetchval("SELECT count(*) FROM st_fts")

            return {
                "total_documents": total_docs or 0,
                "table_type": "postgresql_tsvector",
            }
