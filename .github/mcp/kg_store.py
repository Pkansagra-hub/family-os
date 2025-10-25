"""
Knowledge Graph v2 - SQLite Store

Storage layer for semantic repository graph with:
- SQLite database with FTS5 full-text search
- Vector embeddings for semantic similarity search
- Hybrid search combining FTS5 (BM25) + vector similarity
- Contract validation (JSON Schema)
- Thread-safe operations
- Graph algorithms (BFS, cycle detection)

Usage:
    store = KGStore("path/to/kg_v2.db")
    store.add_node({"node_id": "adr_0051", "node_type": "adr", "label": "Agent Scheduling"})
    store.add_edge({"src": "agent_scheduler", "dst": "adr_0051", "relation": "implements"})
    results = store.search("scheduling")
    results = store.hybrid_search("agent coordination", alpha=0.7)
"""

import json
import sqlite3
import time
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional

import jsonschema

# ============================================================================
# EMBEDDING UTILITIES
# ============================================================================


def generate_embedding(
    text: str, model: str = "sentence-transformers/all-MiniLM-L6-v2"
) -> List[float]:
    """
    Generate vector embedding for text using sentence-transformers

    Args:
        text: Input text to embed
        model: Model name (default: all-MiniLM-L6-v2, 384 dimensions)

    Returns:
        List of floats representing the embedding

    Note:
        Requires: pip install sentence-transformers
        First call will download the model (~80MB)
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. "
            "Install with: pip install sentence-transformers"
        )

    # Cache model instance (avoid reloading)
    if not hasattr(generate_embedding, "_model_cache"):
        generate_embedding._model_cache = {}

    if model not in generate_embedding._model_cache:
        generate_embedding._model_cache[model] = SentenceTransformer(model)

    embedder = generate_embedding._model_cache[model]
    embedding = embedder.encode(text, convert_to_numpy=True)

    return embedding.tolist()


class KGStore:
    """SQLite-based semantic graph store with contract validation"""

    def __init__(self, db_path: str):
        """
        Initialize store

        Args:
            db_path: Path to SQLite database (will be created if not exists)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread-safe connection
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode
        )
        self.conn.row_factory = sqlite3.Row
        self.lock = RLock()

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Initialize schema and load contracts
        self._init_schema()
        self._load_contracts()

    def _init_schema(self):
        """Create tables and indexes if they don't exist"""
        with self.lock:
            self.conn.executescript(
                """
                -- Nodes table
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    file_path TEXT,
                    tags_json TEXT,
                    content_preview TEXT,
                    code_snippet TEXT,
                    created_at REAL NOT NULL,
                    indexed_at REAL NOT NULL
                );

                -- FTS5 virtual table for full-text search
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    node_id UNINDEXED,
                    label,
                    content_preview,
                    tags_json,
                    content='nodes',
                    content_rowid='rowid'
                );

                -- Triggers to keep FTS in sync
                CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
                    INSERT INTO nodes_fts(rowid, node_id, label, content_preview, tags_json)
                    VALUES (new.rowid, new.node_id, new.label, new.content_preview, new.tags_json);
                END;

                CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
                    INSERT INTO nodes_fts(nodes_fts, rowid, node_id, label, content_preview, tags_json)
                    VALUES ('delete', old.rowid, old.node_id, old.label, old.content_preview, old.tags_json);
                END;

                CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
                    INSERT INTO nodes_fts(nodes_fts, rowid, node_id, label, content_preview, tags_json)
                    VALUES ('delete', old.rowid, old.node_id, old.label, old.content_preview, old.tags_json);
                    INSERT INTO nodes_fts(rowid, node_id, label, content_preview, tags_json)
                    VALUES (new.rowid, new.node_id, new.label, new.content_preview, new.tags_json);
                END;

                -- Edges table
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    evidence TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (src) REFERENCES nodes(node_id) ON DELETE CASCADE,
                    FOREIGN KEY (dst) REFERENCES nodes(node_id) ON DELETE CASCADE,
                    UNIQUE(src, dst, relation)
                );

                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
                CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
                CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
                CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
                CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
                CREATE INDEX IF NOT EXISTS idx_edges_src_relation ON edges(src, relation);
                CREATE INDEX IF NOT EXISTS idx_edges_dst_relation ON edges(dst, relation);

                -- Vector embeddings table for semantic search
                CREATE TABLE IF NOT EXISTS node_embeddings (
                    node_id TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    embedding_model TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_embeddings_model ON node_embeddings(embedding_model);
            """
            )

    def _load_contracts(self):
        """Load JSON schemas for validation"""
        contract_dir = Path(__file__).parent.parent / "contracts" / "kg"

        try:
            with open(contract_dir / "node.schema.json", "r", encoding="utf-8") as f:
                self.node_schema = json.load(f)

            with open(contract_dir / "edge.schema.json", "r", encoding="utf-8") as f:
                self.edge_schema = json.load(f)
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Contract files not found: {e}. Run from repository root."
            )

    def add_node(self, node: Dict) -> Dict:
        """
        Add or update a node with contract validation

        Args:
            node: Node data (must match node.schema.json)

        Returns:
            Node data with timestamps

        Raises:
            jsonschema.ValidationError: If node doesn't match schema
        """
        # Validate against contract
        jsonschema.validate(node, self.node_schema)

        # Add timestamps
        if "created_at" not in node:
            node["created_at"] = time.time()
        node["indexed_at"] = time.time()

        # Insert or update
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO nodes (
                    node_id, node_type, label, file_path, tags_json,
                    content_preview, code_snippet, created_at, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_type=excluded.node_type,
                    label=excluded.label,
                    file_path=excluded.file_path,
                    tags_json=excluded.tags_json,
                    content_preview=excluded.content_preview,
                    code_snippet=excluded.code_snippet,
                    indexed_at=excluded.indexed_at
            """,
                (
                    node["node_id"],
                    node["node_type"],
                    node["label"],
                    node.get("file_path"),
                    json.dumps(node.get("tags", [])),
                    node.get("content_preview"),
                    node.get("code_snippet"),
                    node["created_at"],
                    node["indexed_at"],
                ),
            )
            self.conn.commit()  # Explicit commit for persistence

        return node

    def get_node(self, node_id: str) -> Optional[Dict]:
        """
        Get a node by ID

        Args:
            node_id: Node identifier

        Returns:
            Node dict or None if not found
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT * FROM nodes WHERE node_id = ?
            """,
                (node_id,),
            )
            row = cursor.fetchone()

            if row:
                node = dict(row)
                node["tags"] = json.loads(node.pop("tags_json", "[]"))
                return node
            return None

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node and all its edges

        Args:
            node_id: Node to remove

        Returns:
            True if node was removed, False if not found
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                DELETE FROM nodes WHERE node_id = ?
            """,
                (node_id,),
            )
            return cursor.rowcount > 0

    def add_edge(self, edge: Dict) -> Dict:
        """
        Add an edge with contract validation

        Args:
            edge: Edge data (must match edge.schema.json)

        Returns:
            Edge data with timestamp

        Raises:
            jsonschema.ValidationError: If edge doesn't match schema
        """
        # Validate against contract
        jsonschema.validate(edge, self.edge_schema)

        with self.lock:
            self.conn.execute(
                """
                INSERT INTO edges (src, dst, relation, evidence, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(src, dst, relation) DO UPDATE SET
                    evidence=excluded.evidence,
                    created_at=excluded.created_at
            """,
                (
                    edge["src"],
                    edge["dst"],
                    edge["relation"],
                    edge.get("evidence", ""),
                    time.time(),
                ),
            )
            self.conn.commit()  # Explicit commit for persistence

        return edge

    def remove_edge(self, src: str, dst: str, relation: str) -> bool:
        """
        Remove an edge

        Args:
            src: Source node ID
            dst: Destination node ID
            relation: Relation type

        Returns:
            True if edge was removed, False if not found
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                DELETE FROM edges WHERE src = ? AND dst = ? AND relation = ?
            """,
                (src, dst, relation),
            )
            return cursor.rowcount > 0

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Full-text search using FTS5

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of matching nodes (sorted by relevance)
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT n.*, rank
                FROM nodes n
                JOIN nodes_fts ON nodes_fts.node_id = n.node_id
                WHERE nodes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """,
                (query, limit),
            )

            results = []
            for row in cursor.fetchall():
                node = dict(row)
                node["tags"] = json.loads(node.pop("tags_json", "[]"))
                node.pop("rank", None)  # Remove FTS rank from result
                results.append(node)

            return results

    def get_neighbors(
        self, node_id: str, direction: str = "both", relation: Optional[str] = None
    ) -> List[Dict]:
        """
        Get adjacent nodes

        Args:
            node_id: Node to query
            direction: "outgoing", "incoming", or "both"
            relation: Filter by relation type (optional)

        Returns:
            List of neighbor nodes with relation metadata
        """
        with self.lock:
            if direction == "outgoing":
                where_clause = "e.src = ?"
                neighbor_col = "e.dst"
                params = [node_id]
            elif direction == "incoming":
                where_clause = "e.dst = ?"
                neighbor_col = "e.src"
                params = [node_id]
            else:  # both
                where_clause = "(e.src = ? OR e.dst = ?)"
                neighbor_col = "CASE WHEN e.src = ? THEN e.dst ELSE e.src END"
                params = [node_id, node_id, node_id]

            if relation:
                where_clause += " AND e.relation = ?"
                params.append(relation)

            query = f"""
                SELECT DISTINCT n.*, e.relation, e.evidence
                FROM edges e
                JOIN nodes n ON n.node_id = {neighbor_col}
                WHERE {where_clause}
            """

            cursor = self.conn.execute(query, params)

            results = []
            for row in cursor.fetchall():
                node = dict(row)
                node["tags"] = json.loads(node.pop("tags_json", "[]"))
                results.append(node)

            return results

    def find_by_type(self, node_type: str, limit: int = 50) -> List[Dict]:
        """
        Find all nodes of a specific type

        Args:
            node_type: Node type (adr, module, contract, file)
            limit: Max results

        Returns:
            List of nodes
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT * FROM nodes
                WHERE node_type = ?
                ORDER BY indexed_at DESC
                LIMIT ?
            """,
                (node_type, limit),
            )

            results = []
            for row in cursor.fetchall():
                node = dict(row)
                node["tags"] = json.loads(node.pop("tags_json", "[]"))
                results.append(node)

            return results

    def get_graph_summary(self) -> Dict:
        """
        Get high-level statistics about the graph

        Returns:
            Dict with node/edge counts and distributions
        """
        with self.lock:
            # Node counts by type
            cursor = self.conn.execute(
                """
                SELECT node_type, COUNT(*) as count
                FROM nodes
                GROUP BY node_type
            """
            )
            nodes_by_type = {
                row["node_type"]: row["count"] for row in cursor.fetchall()
            }

            # Edge counts by relation
            cursor = self.conn.execute(
                """
                SELECT relation, COUNT(*) as count
                FROM edges
                GROUP BY relation
            """
            )
            edges_by_relation = {
                row["relation"]: row["count"] for row in cursor.fetchall()
            }

            return {
                "nodes_by_type": nodes_by_type,
                "edges_by_relation": edges_by_relation,
                "total_nodes": sum(nodes_by_type.values()),
                "total_edges": sum(edges_by_relation.values()),
            }

    def find_paths(
        self, src: str, dst: str, max_hops: int = 6, max_paths: int = 5
    ) -> List[List[str]]:
        """
        Find paths between two nodes using BFS

        Args:
            src: Source node ID
            dst: Destination node ID
            max_hops: Maximum path length
            max_paths: Maximum number of paths to return

        Returns:
            List of paths (each path is a list of node IDs)
        """
        paths = []
        queue = [(src, [src])]
        visited = set()

        while queue and len(paths) < max_paths:
            current, path = queue.pop(0)

            if len(path) > max_hops:
                continue

            if current == dst:
                paths.append(path)
                continue

            if current in visited:
                continue
            visited.add(current)

            # Get outgoing neighbors
            neighbors = self.get_neighbors(current, direction="outgoing")
            for neighbor in neighbors:
                neighbor_id = neighbor["node_id"]
                if neighbor_id not in path:
                    queue.append((neighbor_id, path + [neighbor_id]))

        return paths

    def get_module_deps(self, module_id: str, depth: Optional[int] = None) -> List[str]:
        """
        Get all dependencies of a module (transitive, BFS)

        Args:
            module_id: Module to analyze
            depth: Maximum depth (None = unlimited)

        Returns:
            List of dependency module IDs
        """
        visited = set()
        queue = [(module_id, 0)]

        while queue:
            current, level = queue.pop(0)

            if current in visited:
                continue
            if depth is not None and level > depth:
                continue

            visited.add(current)

            # Find dependencies
            with self.lock:
                cursor = self.conn.execute(
                    """
                    SELECT dst FROM edges
                    WHERE src = ? AND relation = 'depends_on'
                """,
                    (current,),
                )
                deps = [row["dst"] for row in cursor.fetchall()]

            for dep in deps:
                if dep not in visited:
                    queue.append((dep, level + 1))

        visited.discard(module_id)  # Don't include the module itself
        return list(visited)

    def find_circular_deps(self) -> List[List[str]]:
        """
        Detect circular dependencies using DFS

        Returns:
            List of circular dependency chains
        """
        with self.lock:
            # Get all nodes involved in depends_on relations
            cursor = self.conn.execute(
                """
                SELECT DISTINCT src FROM edges WHERE relation = 'depends_on'
            """
            )
            all_nodes = [row["src"] for row in cursor.fetchall()]

        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]):
            """DFS with cycle detection"""
            if node in rec_stack:
                # Found cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                if cycle not in cycles:
                    cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)

            # Get dependencies
            with self.lock:
                cursor = self.conn.execute(
                    """
                    SELECT dst FROM edges WHERE src = ? AND relation = 'depends_on'
                """,
                    (node,),
                )
                neighbors = [row["dst"] for row in cursor.fetchall()]

            for neighbor in neighbors:
                dfs(neighbor, path + [neighbor])

            rec_stack.discard(node)

        # Try DFS from each node
        for node in all_nodes:
            if node not in visited:
                dfs(node, [node])

        return cycles

    def add_embedding(
        self,
        node_id: str,
        embedding: List[float],
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        """
        Store vector embedding for a node

        Args:
            node_id: Node identifier
            embedding: Vector embedding as list of floats
            model: Name of the embedding model used
        """
        import struct

        # Convert to binary format (array of doubles)
        embedding_blob = struct.pack(f"{len(embedding)}d", *embedding)

        with self.lock:
            self.conn.execute(
                """
                INSERT INTO node_embeddings (node_id, embedding, embedding_model, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    embedding=excluded.embedding,
                    embedding_model=excluded.embedding_model,
                    created_at=excluded.created_at
                """,
                (node_id, embedding_blob, model, time.time()),
            )
            self.conn.commit()  # Explicit commit for persistence

    def get_embedding(self, node_id: str) -> Optional[List[float]]:
        """
        Retrieve vector embedding for a node

        Args:
            node_id: Node identifier

        Returns:
            List of floats representing the embedding, or None if not found
        """
        import struct

        with self.lock:
            cursor = self.conn.execute(
                "SELECT embedding FROM node_embeddings WHERE node_id = ?", (node_id,)
            )
            row = cursor.fetchone()

            if row:
                embedding_blob = row["embedding"]
                # Unpack binary to floats
                num_dims = len(embedding_blob) // 8  # 8 bytes per double
                return list(struct.unpack(f"{num_dims}d", embedding_blob))
            return None

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def vector_search(
        self,
        query_embedding: List[float],
        limit: int = 20,
        node_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Perform vector similarity search

        Args:
            query_embedding: Query vector
            limit: Maximum results to return
            node_type: Optional filter by node type

        Returns:
            List of nodes sorted by similarity score (highest first)
        """
        import struct

        with self.lock:
            # Get all embeddings
            if node_type:
                cursor = self.conn.execute(
                    """
                    SELECT e.node_id, e.embedding, n.*
                    FROM node_embeddings e
                    JOIN nodes n ON e.node_id = n.node_id
                    WHERE n.node_type = ?
                    """,
                    (node_type,),
                )
            else:
                cursor = self.conn.execute(
                    """
                    SELECT e.node_id, e.embedding, n.*
                    FROM node_embeddings e
                    JOIN nodes n ON e.node_id = n.node_id
                    """
                )

            results = []
            for row in cursor.fetchall():
                # Unpack embedding
                embedding_blob = row["embedding"]
                num_dims = len(embedding_blob) // 8
                node_embedding = list(struct.unpack(f"{num_dims}d", embedding_blob))

                # Calculate similarity
                similarity = self.cosine_similarity(query_embedding, node_embedding)

                # Build node dict
                node = dict(row)
                node.pop("embedding", None)  # Remove embedding blob
                node["tags"] = json.loads(node.pop("tags_json", "[]"))
                node["similarity_score"] = similarity

                results.append(node)

            # Sort by similarity (descending)
            results.sort(key=lambda x: x["similarity_score"], reverse=True)

            return results[:limit]

    def hybrid_search(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        alpha: float = 0.5,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Hybrid search combining FTS5 (keyword) and vector (semantic) search

        Args:
            query: Text query for FTS5 search
            query_embedding: Optional pre-computed query embedding for vector search.
                           If None and alpha < 1.0, will auto-generate embedding.
            alpha: Weight for FTS5 vs vector (0.0 = pure vector, 1.0 = pure FTS5)
            limit: Maximum results to return

        Returns:
            List of nodes with combined ranking score
        """
        # FTS5 search
        fts_results = self.search(query, limit=limit * 2)  # Get more for merging
        fts_scores = {
            r["node_id"]: 1.0 - (i / len(fts_results))
            for i, r in enumerate(fts_results)
        }

        # Vector search (generate embedding if needed and not pure FTS5)
        vector_scores = {}
        if alpha < 1.0:  # Only need vector search if not pure FTS5
            if query_embedding is None:
                # Auto-generate embedding from query
                try:
                    query_embedding = generate_embedding(query)
                except ImportError:
                    # Fall back to pure FTS5 if sentence-transformers not available
                    print(
                        "Warning: sentence-transformers not installed, falling back to pure FTS5 search"
                    )
                    alpha = 1.0

            if query_embedding:
                vector_results = self.vector_search(query_embedding, limit=limit * 2)
                vector_scores = {
                    r["node_id"]: r["similarity_score"] for r in vector_results
                }

        # Combine scores
        all_node_ids = set(fts_scores.keys()) | set(vector_scores.keys())
        combined_results = []

        for node_id in all_node_ids:
            fts_score = fts_scores.get(node_id, 0.0)
            vec_score = vector_scores.get(node_id, 0.0)

            # Weighted combination
            combined_score = alpha * fts_score + (1 - alpha) * vec_score

            # Get node data
            node = self.get_node(node_id)
            if node:
                node["hybrid_score"] = combined_score
                node["fts_score"] = fts_score
                node["vector_score"] = vec_score
                combined_results.append(node)

        # Sort by combined score
        combined_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        return combined_results[:limit]

    def close(self):
        """Close database connection"""
        with self.lock:
            self.conn.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


if __name__ == "__main__":
    # Quick test
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    print(f"Testing KGStore with {db_path}")

    store = KGStore(db_path)

    # Add nodes
    store.add_node(
        {
            "node_id": "adr_0051",
            "node_type": "adr",
            "label": "Agent Scheduling",
            "tags": ["scheduling", "agents"],
        }
    )

    store.add_node(
        {
            "node_id": "k1.agent_scheduler",
            "node_type": "module",
            "label": "Agent Scheduler",
            "tags": ["k1", "scheduling"],
        }
    )

    # Add edge
    store.add_edge(
        {
            "src": "k1.agent_scheduler",
            "dst": "adr_0051",
            "relation": "implements",
            "evidence": "Docstring mentions ADR-0051",
        }
    )

    # Search
    results = store.search("scheduling")
    print(f"\nSearch 'scheduling': {len(results)} results")
    for r in results:
        print(f"  - {r['node_id']}: {r['label']}")

    # Neighbors
    neighbors = store.get_neighbors("adr_0051")
    print(f"\nNeighbors of adr_0051: {len(neighbors)} results")
    for n in neighbors:
        print(f"  - {n['node_id']} ({n['relation']})")

    # Summary
    summary = store.get_graph_summary()
    print("\nGraph summary:")
    print(f"  Nodes: {summary['total_nodes']} ({summary['nodes_by_type']})")
    print(f"  Edges: {summary['total_edges']} ({summary['edges_by_relation']})")

    store.close()

    print("\n✅ KGStore basic tests passed!")
    Path(db_path).unlink()
    Path(db_path).unlink()
