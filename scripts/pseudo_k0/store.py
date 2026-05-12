"""scripts.pseudo_k0.store — SQLiteK0Store: append-only WAL + obs_log.

Two tables:

    wal       — One row per envelope received at POST /k0/command.submit.
                Columns extract routing keys (topic, space_id, tenant_id,
                actor_id, band, trace_id, ts) into indexed columns;
                the full body is stored as JSON in ``body`` plus a
                content projection in ``content`` for LIKE search.

    obs_log   — One row per POST /k0/obs.emit. Stores ``kind`` + raw JSON.

Thread-safety: a single ``threading.Lock`` serialises writes; SQLite WAL
journal mode allows concurrent readers. The store is process-local — one
``SQLiteK0Store`` instance per pseudo-K0 server.

Recall semantics (intentionally simple):
    * Each selector in ``RecallRequestBody.selectors`` issues one SQL
      SELECT filtered by ``space_id`` (required) and optional
      ``tenant_id`` / ``topic`` filters.
    * ``selector.type`` is matched against a ``memory_type`` column
      inferred from the envelope topic (see ``_infer_memory_type``).
      Selector type ``"belief"``, ``"graph"``, ``"device"``, ``"session"``
      are accepted but currently match no rows (pseudo-K0 has no graph
      store) — returned as empty hits.
    * ``vector_query`` / ``fts_query`` map to a SQL ``LIKE %query%`` on
      the projected ``content`` column. No real vector search.
    * Aggregate ``max_results`` truncates the merged hit list.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.pseudo_k0.models import (
    K0Envelope,
    RecallHit,
    RecallRequestBody,
    RecallResponseBody,
    RecallSelectorBody,
)

logger = logging.getLogger(__name__)


_DDL = """
CREATE TABLE IF NOT EXISTS wal (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms        INTEGER NOT NULL,
    topic        TEXT    NOT NULL,
    memory_type  TEXT,
    space_id     TEXT    NOT NULL,
    tenant_id    TEXT,
    actor_id     TEXT,
    device_id    TEXT,
    band         TEXT,
    trace_id     TEXT,
    content      TEXT    NOT NULL DEFAULT '',
    body         TEXT    NOT NULL DEFAULT '{}',
    envelope     TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_wal_space        ON wal(space_id);
CREATE INDEX IF NOT EXISTS idx_wal_topic        ON wal(topic);
CREATE INDEX IF NOT EXISTS idx_wal_memory_type  ON wal(memory_type);
CREATE INDEX IF NOT EXISTS idx_wal_actor        ON wal(actor_id);
CREATE INDEX IF NOT EXISTS idx_wal_tenant       ON wal(tenant_id);

CREATE TABLE IF NOT EXISTS obs_log (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms  INTEGER NOT NULL,
    kind   TEXT NOT NULL,
    body   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_obs_kind ON obs_log(kind);
"""


def _infer_memory_type(topic: str, body: Dict[str, Any]) -> Optional[str]:
    """Best-effort projection of envelope topic + body → ``memory_type`` tag.

    For ``memory.write.v1`` the body's ``activity_type`` or top-level
    ``type`` is inspected. Recall returns hits keyed off this column.
    """
    # Explicit body hints first.
    for key in ("memory_type", "type"):
        v = body.get(key)
        if isinstance(v, str) and v:
            return v.lower()
    # Topic-based fallback. Match against canonical k0 selector kinds.
    t = topic.lower()
    if t.startswith("memory.write"):
        # Default memory.write.v1 envelopes to "episodic" so they show
        # up in selector.type="episodic" queries.
        return "episodic"
    if t.startswith("belief"):
        return "belief"
    return None


def _extract_content(body: Dict[str, Any]) -> str:
    """Pull a human-readable content projection out of an envelope body."""
    for key in ("content", "summary", "text", "title", "description"):
        v = body.get(key)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            inner = v.get("text") or v.get("summary")
            if isinstance(inner, str) and inner:
                return inner
    # Fallback: compact JSON of the body (truncated).
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw[:1024]


class SQLiteK0Store:
    """Thread-safe SQLite store for pseudo-K0 WAL + obs_log."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # ``check_same_thread=False`` lets the FastAPI thread pool reuse
        # the connection; the ``_lock`` above serialises mutators.
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        with self._lock:
            self._conn.executescript(_DDL)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:  # pragma: no cover — defensive
                logger.debug("close: sqlite error", exc_info=True)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def write_envelope(self, envelope: K0Envelope) -> int:
        """Append a command-submit envelope to the WAL. Returns the row id."""
        body = envelope.body or {}
        memory_type = _infer_memory_type(envelope.topic, body)
        content = _extract_content(body)
        body_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        envelope_json = json.dumps(
            envelope.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        ts_ms = int(time.time() * 1000)
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO wal (
                    ts_ms, topic, memory_type, space_id, tenant_id,
                    actor_id, device_id, band, trace_id,
                    content, body, envelope
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_ms,
                    envelope.topic,
                    memory_type,
                    envelope.space_id or "default",
                    envelope.tenant_id,
                    envelope.actor,
                    envelope.device_id,
                    envelope.band,
                    envelope.cognitive_trace_id,
                    content,
                    body_json,
                    envelope_json,
                ),
            )
            return int(cur.lastrowid or 0)

    def write_obs(self, kind: str, body: Dict[str, Any]) -> int:
        """Append an obs.emit payload to obs_log. Returns the row id."""
        body_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ts_ms = int(time.time() * 1000)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO obs_log (ts_ms, kind, body) VALUES (?, ?, ?)",
                (ts_ms, kind, body_json),
            )
            return int(cur.lastrowid or 0)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def recall(self, request: RecallRequestBody) -> RecallResponseBody:
        """Execute a ``recall.request.v1`` body, returning the response body."""
        started_ms = time.time() * 1000
        space_id = request.space_id
        tenant_id = request.tenant_id

        merged: List[RecallHit] = []
        for selector in request.selectors:
            hits = self._recall_selector(
                selector=selector,
                space_id=space_id,
                tenant_id=tenant_id,
                fallback_query=request.vector_query or request.fts_query,
            )
            merged.extend(hits)

        total = len(merged)
        truncated = total > request.max_results
        if truncated:
            merged = merged[: request.max_results]
        latency_ms = max(0, int(time.time() * 1000 - started_ms))
        return RecallResponseBody(
            hits=merged,
            total=total,
            latency_ms=latency_ms,
            truncated=truncated,
            trace_id=request.trace_id,
        )

    def _recall_selector(
        self,
        *,
        selector: RecallSelectorBody,
        space_id: str,
        tenant_id: Optional[str],
        fallback_query: Optional[str],
    ) -> List[RecallHit]:
        """Run a single selector against the WAL."""
        sel_type = selector.type.lower()
        # Selector kinds with no backing store in pseudo-K0.
        if sel_type in {"belief", "graph", "device", "session"}:
            return []

        query_text = selector.query or fallback_query
        sql = (
            "SELECT id, ts_ms, topic, memory_type, content, body, "
            "       actor_id, trace_id, tenant_id "
            "FROM wal "
            "WHERE space_id = :space_id "
            "  AND (:memory_type IS NULL OR memory_type = :memory_type) "
            "  AND (:topic_filter IS NULL OR topic = :topic_filter) "
            "  AND (:tenant_id IS NULL OR tenant_id = :tenant_id OR tenant_id IS NULL) "
            "  AND (:query_like IS NULL OR content LIKE :query_like) "
            "ORDER BY id DESC "
            "LIMIT :limit"
        )
        params: Dict[str, Any] = {
            "space_id": space_id,
            "memory_type": sel_type,
            "topic_filter": selector.topic,
            "tenant_id": tenant_id,
            "query_like": f"%{query_text}%" if query_text else None,
            "limit": int(selector.limit),
        }
        with self._lock:
            cur = self._conn.execute(sql, params)
            rows: List[sqlite3.Row] = cur.fetchall()

        hits: List[RecallHit] = []
        for row in rows:
            try:
                body_dict = json.loads(row["body"] or "{}")
            except json.JSONDecodeError:
                body_dict = {}
            hits.append(
                RecallHit(
                    atom_id=f"wal:{row['id']}",
                    content=body_dict or {"content": row["content"]},
                    score=1.0,  # pseudo-K0 has no real scoring
                    source="pseudo_k0.wal",
                    selector_type=sel_type,
                    cursor=None,
                )
            )
        return hits

    # ------------------------------------------------------------------
    # Diagnostics (used by /healthz and tests)
    # ------------------------------------------------------------------
    def counts(self) -> Tuple[int, int]:
        """Return ``(wal_rows, obs_rows)``."""
        with self._lock:
            wal = self._conn.execute("SELECT COUNT(*) AS n FROM wal").fetchone()["n"]
            obs = self._conn.execute("SELECT COUNT(*) AS n FROM obs_log").fetchone()["n"]
        return int(wal), int(obs)


__all__ = ["SQLiteK0Store", "_infer_memory_type", "_extract_content"]
