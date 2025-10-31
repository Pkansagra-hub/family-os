"""FTS (Full Text Search) storage operations using SQLite FTS5."""

from __future__ import annotations

import json
import logging
from typing import Any

from k0.uow.connection_pool import connection_scope

LOGGER = logging.getLogger(__name__)


class FtsStore:
    """Storage operations for FTS virtual table."""

    def __init__(self) -> None:
        pass

    def index_wal_entry(
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

        with connection_scope() as connection:
            connection.execute(
                """
				INSERT OR REPLACE INTO st_fts (
					wal_pos, tenant_id, space_id, topic, content,
					envelope_json, body, payload_sha256, schema_uri,
					schema_version, device_id, commit_ts
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
                (
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
                ),
            )

    def remove_wal_entry(self, *, wal_pos: int) -> None:
        """Remove a WAL entry from the FTS index."""
        with connection_scope() as connection:
            connection.execute("DELETE FROM st_fts WHERE wal_pos = ?", (wal_pos,))

    def search(
        self,
        *,
        query: str,
        space_id: str,
        tenant_id: str | None = None,
        topic: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search the FTS index and return matching entries."""
        with connection_scope() as connection:
            params = []
            query_parts = [
                "SELECT wal_pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, schema_uri, schema_version, device_id, commit_ts, bm25(st_fts) as score",
                "FROM st_fts",
                "WHERE st_fts MATCH ?",
                "AND space_id = ?",
            ]

            if tenant_id:
                query_parts.append("AND tenant_id = ?")
                params.append(tenant_id)

            if topic:
                query_parts.append("AND topic = ?")
                params.append(topic)

            query_parts.append("ORDER BY bm25(st_fts)")
            query_parts.append("LIMIT ?")

            statement = " ".join(query_parts)
            params.extend([query, space_id, limit])

            rows = connection.execute(statement, params).fetchall()

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

    def get_stats(self) -> dict[str, Any]:
        """Get FTS table statistics."""
        with connection_scope() as connection:
            cursor = connection.execute("SELECT count(*) as total_docs FROM st_fts")
            total_docs = cursor.fetchone()[0]

            return {
                "total_documents": total_docs,
                "table_type": "fts5",
            }
