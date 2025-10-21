# memory_server.py
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss  # type: ignore
import numpy as np
from mcp.server.fastmcp import FastMCP

DB_PATH = Path(os.environ.get("MEM_DB", Path.home() / ".mcp_memories" / "mem.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)  # goes to stderr (safe for MCP)

# Optional allow-list for project names: "projA,projB"
_ALLOWED = set(
    p.strip()
    for p in os.environ.get("MEM_ALLOWED_PROJECTS", "").split(",")
    if p.strip()
)

_AUTO_EMBED = os.environ.get("MEM_AUTO_EMBED", "1").lower() not in {"0", "false", "no"}
_EMBED_DIM = max(8, int(os.environ.get("MEM_EMBED_DIM", "256")))

mcp = FastMCP("memories")


@dataclass
class Memory:
    id: str
    project: str
    title: str
    content: str
    tags: List[str]
    links: List[Dict[str, str]]
    created_at: float
    updated_at: float
    deleted_at: Optional[float]
    band: str  # "GREEN|AMBER|RED|BLACK"


def _connect():
    # fresh connection per call; WAL + FKs enabled
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def _init():
    con = _connect()
    cur = con.cursor()

    # Core tables
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS memories(
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL,
            band TEXT NOT NULL DEFAULT 'GREEN',
            sha256 TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_vectors(
            memory_id TEXT PRIMARY KEY,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
        );
        """
    )

    # --- MIGRATE links → add FK CASCADE if missing ---
    # Ensure 'links' table exists before migration logic
    row = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='links'"
    ).fetchone()
    links_sql = row["sql"] if row else ""
    if not links_sql:
        # Create the links table if it doesn't exist at all
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS links(
                src TEXT NOT NULL,
                dest TEXT NOT NULL,
                relation TEXT NOT NULL,
                PRIMARY KEY (src, dest, relation),
                FOREIGN KEY (src) REFERENCES memories(id) ON DELETE CASCADE,
                FOREIGN KEY (dest) REFERENCES memories(id) ON DELETE CASCADE
            );
            """
        )
        links_sql = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='links'"
        ).fetchone()["sql"]

    if "FOREIGN KEY" not in (links_sql or ""):
        # Only attempt to copy data if the old 'links' table exists
        # and has no FK constraints
        # Defensive: check if 'links' table exists before copying
        cur.executescript(
            """
            PRAGMA foreign_keys=OFF;
            BEGIN;
            CREATE TABLE IF NOT EXISTS links_new(
                src TEXT NOT NULL,
                dest TEXT NOT NULL,
                relation TEXT NOT NULL,
                PRIMARY KEY (src, dest, relation),
                FOREIGN KEY (src) REFERENCES memories(id) ON DELETE CASCADE,
                FOREIGN KEY (dest) REFERENCES memories(id) ON DELETE CASCADE
            );
            INSERT OR IGNORE INTO links_new(src,dest,relation)
              SELECT l.src, l.dest, l.relation
                FROM links AS l
                JOIN memories ms ON ms.id = l.src
                JOIN memories md ON md.id = l.dest;
            DROP TABLE IF EXISTS links;
            ALTER TABLE links_new RENAME TO links;
            COMMIT;
            PRAGMA foreign_keys=ON;
            """
        )

    existing_fts = cur.execute(
        """
        SELECT sql FROM sqlite_master
         WHERE type='table' AND name='memories_fts'
        """
    ).fetchone()
    if (
        existing_fts
        and existing_fts["sql"]
        and "content='memories'" in existing_fts["sql"]
    ):
        cur.executescript(
            """
            DROP TABLE IF EXISTS memories_fts;
            DROP TABLE IF EXISTS memories_fts_data;
            DROP TABLE IF EXISTS memories_fts_idx;
            DROP TABLE IF EXISTS memories_fts_docsize;
            DROP TABLE IF EXISTS memories_fts_config;
            """
        )

    cur.executescript(
        """
        DROP TRIGGER IF EXISTS memories_ai;
        DROP TRIGGER IF EXISTS memories_au;
        DROP TRIGGER IF EXISTS memories_ad;
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(title, content, tags, tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid,title,content,tags)
            VALUES (new.rowid,new.title,new.content,new.tags_json);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            DELETE FROM memories_fts WHERE rowid=old.rowid;
            INSERT INTO memories_fts(rowid,title,content,tags)
            VALUES (new.rowid,new.title,new.content,new.tags_json);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            DELETE FROM memories_fts WHERE rowid=old.rowid;
        END;
        """
    )

    fts_count = cur.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='memories_fts'"
    ).fetchone()[0]
    if fts_count:
        populated = cur.execute("SELECT count(*) FROM memories_fts").fetchone()[0]
        if populated == 0:
            cur.execute(
                """
                INSERT INTO memories_fts(rowid,title,content,tags)
                SELECT rowid, title, content, tags_json FROM memories
                WHERE deleted_at IS NULL
                """
            )

    con.commit()
    con.close()


_faiss_lock = threading.RLock()
_faiss_index: Optional[faiss.IndexIDMap2] = None
_faiss_dim: Optional[int] = None
_faiss_id_to_memory: Dict[int, str] = {}


def _faiss_int(memory_id: str) -> int:
    return uuid.UUID(memory_id).int & ((1 << 63) - 1)


def _ensure_faiss_index(dim: int) -> None:
    global _faiss_index, _faiss_dim
    if _faiss_index is None:
        base = faiss.IndexFlatIP(dim)
        _faiss_index = faiss.IndexIDMap2(base)
        _faiss_dim = dim
    elif _faiss_dim != dim:
        raise ValueError(
            f"Faiss index dimension {_faiss_dim} does not match vector dimension {dim}"
        )


def _faiss_add(memory_id: str, vector: np.ndarray) -> None:
    global _faiss_index
    if _faiss_index is None:
        raise RuntimeError("Faiss index has not been initialised")
    faiss_id = _faiss_int(memory_id)
    # Remove stale entries before re-adding
    _faiss_index.remove_ids(np.array([faiss_id], dtype="int64"))
    _faiss_index.add_with_ids(
        vector.reshape(1, -1), np.array([faiss_id], dtype="int64")
    )
    _faiss_id_to_memory[faiss_id] = memory_id


def _faiss_remove(memory_id: str) -> None:
    if _faiss_index is None:
        return
    faiss_id = _faiss_int(memory_id)
    _faiss_index.remove_ids(np.array([faiss_id], dtype="int64"))
    _faiss_id_to_memory.pop(faiss_id, None)


def _load_faiss_index() -> None:
    global _faiss_index, _faiss_dim, _faiss_id_to_memory
    with _faiss_lock:
        con = _connect()
        cur = con.cursor()
        rows = cur.execute(
            """
            SELECT mv.memory_id, mv.dim, mv.vector
              FROM memory_vectors AS mv
              JOIN memories AS m ON m.id = mv.memory_id
             WHERE m.deleted_at IS NULL
            """
        ).fetchall()
        con.close()

        if not rows:
            _faiss_index = None
            _faiss_dim = None
            _faiss_id_to_memory = {}
            return

        dim = rows[0]["dim"]
        for row in rows:
            if row["dim"] != dim:
                raise ValueError(
                    "Inconsistent vector dimensions detected in memory_vectors"
                )

        base = faiss.IndexFlatIP(dim)
        index = faiss.IndexIDMap2(base)
        ids = []
        vectors = []
        mapping: Dict[int, str] = {}
        for row in rows:
            vec = np.frombuffer(row["vector"], dtype=np.float32)
            if vec.shape[0] != dim:
                raise ValueError(
                    "Stored vector length does not match recorded dimension"
                )
            faiss_id = _faiss_int(row["memory_id"])
            ids.append(faiss_id)
            vectors.append(vec)
            mapping[faiss_id] = row["memory_id"]

        vectors_np = np.vstack(vectors)
        faiss.normalize_L2(vectors_np)
        index.add_with_ids(vectors_np, np.array(ids, dtype="int64"))
        _faiss_index = index
        _faiss_dim = dim
        _faiss_id_to_memory = mapping


def _hash(project: str, title: str, content: str, tags: List[str]) -> str:
    h = hashlib.sha256()
    h.update(project.encode())
    h.update(b"\x1f")
    h.update(title.encode())
    h.update(b"\x1f")
    h.update(content.encode())
    h.update(b"\x1f")
    h.update("|".join(tags).encode())
    return h.hexdigest()


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        project=row["project"],
        title=row["title"],
        content=row["content"],
        tags=json.loads(row["tags_json"]),
        links=[],  # populated by helper when needed
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        band=row["band"],
    )


def _require_allowed(project: str):
    if _ALLOWED and project not in _ALLOWED:
        raise PermissionError(f"project '{project}' not allowed")


_init()
_load_faiss_index()


def _generate_embedding_from_text(
    title: str, content: str, tags: List[str]
) -> np.ndarray:
    full_text = " ".join(filter(None, [title, content, " ".join(tags)]))
    tokens = re.findall(r"\b\w+\b", full_text.lower())
    if not tokens:
        tokens = ["empty"]

    vec = np.zeros(_EMBED_DIM, dtype=np.float32)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        # Use first 8 bytes for position, next byte for sign
        idx = int.from_bytes(digest[:8], "big") % _EMBED_DIM
        sign = 1.0 if digest[8] & 1 else -1.0
        vec[idx] += sign

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _auto_embed_memory(
    memory_id: str, title: str, content: str, tags: List[str]
) -> None:
    if not _AUTO_EMBED:
        return
    try:
        vector = _generate_embedding_from_text(title, content, tags)
        _upsert_embedding_internal(memory_id, vector, normalize=False)
    except Exception as exc:  # pragma: no cover - defensive safeguard
        logging.error("auto-embedding failed for %s: %s", memory_id, exc, exc_info=True)


def _upsert_embedding_internal(
    memory_id: str, vector: np.ndarray, normalize: bool = True
) -> bool:
    """Internal helper to upsert embeddings without MCP tool overhead."""
    con = _connect()
    try:
        cur = con.cursor()
        row = cur.execute(
            "SELECT project, deleted_at FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        if not row or row["deleted_at"] is not None:
            return False

        vec = vector.copy()
        if normalize:
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm

        blob = vec.tobytes()
        dim = vec.shape[0]
        now = time.time()

        with _faiss_lock:
            _ensure_faiss_index(dim)
            cur.execute(
                """
                INSERT INTO memory_vectors(memory_id, dim, vector, updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(memory_id) DO UPDATE
                  SET dim=excluded.dim,
                      vector=excluded.vector,
                      updated_at=excluded.updated_at
                """,
                (memory_id, dim, blob, now),
            )
            con.commit()
            _faiss_add(memory_id, vec)
        return True
    finally:
        con.close()


# _vector_from_list removed - only used internally now


def _bm25_norm(x: Optional[float]) -> float:
    """Normalize BM25 score to [0,1] range. Lower BM25 is better."""
    if x is None:
        return 0.0
    if x < 0:
        x = 0.0
    return 1.0 / (1.0 + x)


def _vector_hits_for_query_text(qtext: str, top_k: int) -> List[Tuple[str, float]]:
    """Get vector similarity hits for query text."""
    vec = _generate_embedding_from_text(qtext, "", [])
    with _faiss_lock:
        if _faiss_index is None or _faiss_dim is None:
            return []
        if vec.shape[0] != _faiss_dim:
            return []
        query = np.ascontiguousarray(vec.reshape(1, -1))
        dists, inds = _faiss_index.search(query, top_k)
    out: List[Tuple[str, float]] = []
    for idx, score in zip(inds[0], dists[0]):
        mid = _faiss_id_to_memory.get(int(idx))
        if mid:
            # Convert inner product ([-1..1] approx) to [0..1]
            sim = float(score)
            sim01 = max(0.0, min(1.0, (sim + 1.0) / 2.0))
            out.append((mid, sim01))
    return out


def _hybrid_recall(
    query: str,
    project: Optional[str],
    tag: Optional[str],
    limit: int,
    alpha: float = 0.5,
) -> List[Dict[str, Any]]:
    """Hybrid recall combining BM25 (FTS) and FAISS vector search."""
    # 1) FTS (bm25 lower→better). Pull a wider beam to merge well.
    fts = mem_search(query, project=project, tag=tag, limit=max(limit * 5, 50))
    fts_map: Dict[str, Dict[str, Any]] = {h["id"]: h for h in fts}

    # 2) Vector search via FAISS
    vec_pairs = _vector_hits_for_query_text(query, top_k=max(limit * 5, 50))
    vec_map: Dict[str, float] = {mid: score for mid, score in vec_pairs}

    # 3) Merge with weighted score
    all_ids = list({*fts_map.keys(), *vec_map.keys()})
    if not all_ids:
        return []

    # Load metadata/snippets for candidates that came only from vector side
    missing = [mid for mid in all_ids if mid not in fts_map]
    if missing:
        full = mem_read_many(missing)
        for m in full:
            fts_map[m["id"]] = {
                "id": m["id"],
                "project": m["project"],
                "title": m["title"],
                "updated_at": m["updated_at"],
                "snippet": (
                    m["content"][:160] + ("…" if len(m["content"]) > 160 else "")
                ),
                "score": None,  # bm25 unknown
            }

    merged: List[Dict[str, Any]] = []
    for mid in all_ids:
        f = fts_map.get(mid)
        if not f:
            continue
        bm25_norm = _bm25_norm(f.get("score"))
        vec_norm = vec_map.get(mid, 0.0)
        hybrid = alpha * bm25_norm + (1.0 - alpha) * vec_norm
        merged.append(
            {
                "id": mid,
                "project": f["project"],
                "title": f["title"],
                "updated_at": f["updated_at"],
                "snippet": f["snippet"],
                "score": float(hybrid),
                "scores": {"fts": float(bm25_norm), "vector": float(vec_norm)},
            }
        )

    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged[:limit]


@mcp.tool()
def mem_write(
    project: str,
    title: str,
    content: str,
    tags: Optional[List[str]] = None,
    band: str = "GREEN",
    upsert_if_same_hash: bool = True,
) -> Dict[str, Any]:
    """Create a memory note for the given project. Returns the stored record."""
    _require_allowed(project)
    tags = tags or []
    now = time.time()
    sha = _hash(project, title, content, tags)
    con = _connect()
    cur = con.cursor()

    if upsert_if_same_hash:
        row = cur.execute(
            "SELECT id FROM memories WHERE sha256=? AND deleted_at IS NULL", (sha,)
        ).fetchone()
        if row:
            mid = row["id"]
            cur.execute("UPDATE memories SET updated_at=? WHERE id=?", (now, mid))
            con.commit()
            con.close()
            return {"status": "updated_touch", "id": mid}

    mid = str(uuid.uuid4())
    cur.execute(
        """
      INSERT INTO memories(id,project,title,content,tags_json,created_at,updated_at,deleted_at,band,sha256)
      VALUES(?,?,?,?,?,?,?,NULL,?,?)
    """,
        (
            mid,
            project,
            title,
            content,
            json.dumps(tags),
            now,
            now,
            band,
            sha,
        ),
    )
    con.commit()
    con.close()
    if _AUTO_EMBED:
        _auto_embed_memory(mid, title, content, tags)
    return {"status": "created", "id": mid}


@mcp.tool()
def mem_read(id: str) -> Dict[str, Any]:
    """Fetch a memory by id."""
    con = _connect()
    cur = con.cursor()
    row = cur.execute(
        "SELECT * FROM memories WHERE id=? AND deleted_at IS NULL", (id,)
    ).fetchone()
    if not row:
        con.close()
        return {"error": "not_found"}
    _require_allowed(row["project"])
    mem = _row_to_memory(row)
    links = cur.execute(
        "SELECT dest, relation FROM links WHERE src=?", (id,)
    ).fetchall()
    mem.links = [{"dest": r["dest"], "relation": r["relation"]} for r in links]
    con.close()
    return asdict(mem)


@mcp.tool()
def mem_update(
    id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[List[str]] = None,
    band: Optional[str] = None,
) -> Dict[str, Any]:
    """Patch fields on a memory."""
    con = _connect()
    cur = con.cursor()
    row = cur.execute(
        "SELECT * FROM memories WHERE id=? AND deleted_at IS NULL", (id,)
    ).fetchone()
    if not row:
        con.close()
        return {"error": "not_found"}
    _require_allowed(row["project"])
    current = _row_to_memory(row)

    new_title = title or current.title
    new_content = content or current.content
    new_tags = tags if tags is not None else current.tags
    new_band = band or current.band
    now = time.time()
    sha = _hash(current.project, new_title, new_content, new_tags)

    cur.execute(
        """
      UPDATE memories SET title=?, content=?, tags_json=?, updated_at=?, band=?, sha256=?
      WHERE id=?
    """,
        (
            new_title,
            new_content,
            json.dumps(new_tags),
            now,
            new_band,
            sha,
            id,
        ),
    )
    con.commit()
    con.close()
    if _AUTO_EMBED:
        _auto_embed_memory(id, new_title, new_content, new_tags)
    return {"status": "updated", "id": id}


@mcp.tool()
def mem_delete(id: str, hard: bool = True) -> Dict[str, Any]:
    """Delete a memory everywhere. Hard by default."""
    con = _connect()
    cur = con.cursor()
    row = cur.execute("SELECT project FROM memories WHERE id=?", (id,)).fetchone()
    if not row:
        con.close()
        return {"status": "noop", "id": id, "hard": hard}

    _require_allowed(row["project"])

    with _faiss_lock:
        cur.execute("DELETE FROM memory_vectors WHERE memory_id=?", (id,))
        _faiss_remove(id)

    # Also clear any links where this id is src or dest (FK CASCADE handles this too, but safe for older DBs)
    cur.execute("DELETE FROM links WHERE src=? OR dest=?", (id, id))

    if hard:
        cur.execute("DELETE FROM memories WHERE id=?", (id,))
    else:
        cur.execute("UPDATE memories SET deleted_at=? WHERE id=?", (time.time(), id))

    con.commit()
    con.close()
    return {"status": "deleted", "id": id, "hard": hard, "vector_removed": True}


@mcp.tool()
def mem_link(src_id: str, dest_id: str, relation: str = "refers_to") -> Dict[str, Any]:
    """Create a relationship from one memory to another (e.g., 'supersedes')."""
    con = _connect()
    cur = con.cursor()

    src = cur.execute(
        "SELECT project FROM memories WHERE id=? AND deleted_at IS NULL", (src_id,)
    ).fetchone()
    if not src:
        con.close()
        return {"error": "src_not_found"}
    dest = cur.execute(
        "SELECT project FROM memories WHERE id=? AND deleted_at IS NULL", (dest_id,)
    ).fetchone()
    if not dest:
        con.close()
        return {"error": "dest_not_found"}

    _require_allowed(src["project"])
    _require_allowed(dest["project"])

    cur.execute(
        "INSERT OR REPLACE INTO links(src,dest,relation) VALUES(?,?,?)",
        (src_id, dest_id, relation),
    )
    con.commit()
    con.close()
    return {"status": "linked", "src": src_id, "dest": dest_id, "relation": relation}


@mcp.tool()
def mem_search(
    query: str,
    project: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Full-text search across stored memories.

    - When `query` is provided (and not `"*"`) the FTS5 virtual table performs a
        BM25-ranked search over titles, content, and tags and returns a snippet as
        well as a numeric `score` (lower is better).
    - When `query` is empty or `"*"`, the latest non-deleted memories are
        returned in reverse chronological order without invoking FTS.

    The result set is deliberately lightweight: id, project, title, snippet,
    updated timestamp, and optional score. Use `mem_read_many` for full bodies.
    """
    con = _connect()
    cur = con.cursor()
    if project:
        _require_allowed(project)

    use_fts = bool(query and query.strip() and query.strip() != "*")

    if use_fts:
        sql = """
     SELECT m.id, m.project, m.title, m.updated_at,
         snippet(memories_fts, 1, '<b>', '</b>', '…', 8) AS snippet,
         bm25(memories_fts) AS score
          FROM memories_fts
          JOIN memories m ON m.rowid = memories_fts.rowid
         WHERE memories_fts MATCH ? AND m.deleted_at IS NULL
        """
        params: List[Any] = [query]
        if project:
            sql += " AND m.project = ?"
            params.append(project)
        if tag:
            sql += """
              AND EXISTS (
                SELECT 1 FROM json_each(m.tags_json) j WHERE j.value = ?
              )
            """
            params.append(tag)
        sql += " ORDER BY score ASC, m.updated_at DESC LIMIT ?"
        params.append(limit)
        rows = cur.execute(sql, tuple(params)).fetchall()
        con.close()
        return [
            {
                **dict(row),
                "score": float(row["score"]) if row["score"] is not None else None,
            }
            for row in rows
        ]

    # Non-FTS fallback: latest docs, simple snippet from content
    sql = """
      SELECT id, project, title, updated_at,
             substr(content, 1, 160) || '…' AS snippet
        FROM memories
       WHERE deleted_at IS NULL
    """
    params: List[Any] = []
    if project:
        sql += " AND project = ?"
        params.append(project)
    if tag:
        sql += """
          AND EXISTS (SELECT 1 FROM json_each(tags_json) j WHERE j.value = ?)
        """
        params.append(tag)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = cur.execute(sql, tuple(params)).fetchall()
    con.close()
    result: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data.setdefault("score", None)
        result.append(data)
    return result


@mcp.tool()
def mem_read_many(ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch multiple memories at once. Returns full records (including content)."""
    if not ids:
        return []
    con = _connect()
    cur = con.cursor()
    # Check allowed projects (fast path: fetch ids -> projects)
    placeholders = ",".join("?" for _ in ids)
    prj_rows = cur.execute(
        f"SELECT id, project FROM memories WHERE id IN ({placeholders}) AND deleted_at IS NULL",
        tuple(ids),
    ).fetchall()
    found_ids = {r["id"] for r in prj_rows}
    for r in prj_rows:
        _require_allowed(r["project"])

    if not found_ids:
        con.close()
        return []

    rows = cur.execute(
        f"SELECT * FROM memories WHERE id IN ({placeholders}) AND deleted_at IS NULL",
        tuple(ids),
    ).fetchall()
    # hydrate links per item
    out: List[Dict[str, Any]] = []
    for row in rows:
        mem = _row_to_memory(row)
        links = cur.execute(
            "SELECT dest, relation FROM links WHERE src=?", (mem.id,)
        ).fetchall()
        mem.links = [{"dest": r["dest"], "relation": r["relation"]} for r in links]
        out.append(asdict(mem))
    con.close()
    return out


# Internal embedding helpers - no longer exposed as MCP tools


@mcp.tool()
def mem_find(
    query: Optional[str] = None,
    project: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 20,
    alpha: float = 0.5,
) -> Dict[str, Any]:
    """Hybrid recall (BM25 ⊕ FAISS). Returns ranked hits + a next_action hint."""
    q = (query or "").strip()
    if not q:
        # fall back to latest docs (no FTS match)
        latest = mem_search("*", project=project, tag=tag, limit=limit)
        return {
            "hits": latest,
            "meta": {
                "query": q,
                "project": project,
                "tag": tag,
                "limit": limit,
                "mode": "recent",
            },
            "next_action": {
                "tool": "mem_read_many",
                "args": {"ids": [h["id"] for h in latest[: min(len(latest), 5)]]},
            },
        }

    hits = _hybrid_recall(q, project=project, tag=tag, limit=limit, alpha=alpha)
    return {
        "hits": hits,
        "meta": {
            "query": q,
            "project": project,
            "tag": tag,
            "limit": limit,
            "mode": "hybrid",
            "alpha": alpha,
        },
        "next_action": {
            "tool": "mem_read_many",
            "args": {"ids": [h["id"] for h in hits[: min(len(hits), 5)]]},
        },
    }


# mem_find_and_read removed - use mem_find + mem_read_many pattern instead


# ---------- Resources (read-only feeds) ----------
@mcp.resource("mem://recent/{project}")
def res_recent(project: str) -> List[Dict[str, Any]]:
    """Latest 25 memories for a project."""
    _require_allowed(project)
    con = _connect()
    cur = con.cursor()
    rows = cur.execute(
        """
      SELECT id, title, updated_at, tags_json FROM memories
       WHERE project=? AND deleted_at IS NULL
       ORDER BY updated_at DESC LIMIT 25
    """,
        (project,),
    ).fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "updated_at": r["updated_at"],
            "tags": json.loads(r["tags_json"]),
        }
        for r in rows
    ]


@mcp.resource("mem://tag/{project}/{tag}")
def res_tag(project: str, tag: str) -> List[Dict[str, Any]]:
    """Latest 25 memories for a project filtered by a tag (no FTS wildcard)."""
    _require_allowed(project)
    con = _connect()
    cur = con.cursor()
    rows = cur.execute(
        """
      SELECT id, title, updated_at, tags_json
        FROM memories AS m
       WHERE m.project=? AND m.deleted_at IS NULL
         AND EXISTS (SELECT 1 FROM json_each(m.tags_json) j WHERE j.value = ?)
       ORDER BY updated_at DESC LIMIT 25
    """,
        (project, tag),
    ).fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "updated_at": r["updated_at"],
            "tags": json.loads(r["tags_json"]),
        }
        for r in rows
    ]


# ---------- Prompt (a reusable, discoverable template) ----------
@mcp.prompt(
    name="memory.context",
    description="Summarise the most relevant memories for a task with timestamped citations",
)
def memory_context(
    task: str, project: Optional[str] = None, tags: Optional[List[str]] = None
) -> str:
    """Build a compact prompt that threads the task with recent, relevant memories."""
    tags = tags or []
    hits = mem_search(task, project=project, tag=(tags[0] if tags else None), limit=10)
    lines = [f"# Task\n{task}\n"]
    if project:
        lines.append(f"# Project\n{project}\n")
    if tags:
        lines.append(f"# Tags\n{', '.join(tags)}\n")

    lines.append("# Context (top hits)")
    if not hits:
        lines.append("- No relevant memories found yet.")
    else:
        for h in hits:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(h["updated_at"]))
            lines.append(f"- [{when}] {h['title']} (id: {h['id']}) — {h['snippet']}")
    lines.append(
        "\n# Instructions\nRespond to the task using the context above. Cite memory IDs in your answer and call `mem_read_many` if you need full bodies."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
