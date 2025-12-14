"""
User Knowledge Graph Query Interface

Provides high-level API for querying User KG without writing raw SQL.
Includes caching, connection pooling, and thread-safety.

Performance:
- Query latency: <10ms P95 target
- Cache duration: 60s for repeated queries
- Thread-safe for concurrent agent access

Reference: docs/plans/chat_experience_poc_plan.md Epic 1.4
"""

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .kg_schema import SCHEMA_SQL, EdgeType, NodeType, validate_node_properties


class UserKG:
    """
    User Knowledge Graph query interface with caching and connection pooling.

    Thread-safe singleton for accessing user's digital twin graph.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        """Singleton pattern: Only one UserKG instance per process"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(UserKG, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize User KG with SQLite database.

        Args:
            db_path: Path to SQLite database file (default: user_kg.db in config/)
        """
        # Only initialize once
        if hasattr(self, "_initialized") and self._initialized:
            return

        # Default db_path relative to config directory
        if db_path is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
            config_dir.mkdir(exist_ok=True)
            db_path = str(config_dir / "user_kg.db")

        self.db_path = db_path
        self._cache: Dict[str, tuple[Any, float]] = {}  # (result, expiry_timestamp)
        self._cache_duration = 60.0  # 60 seconds cache
        self._cache_lock = threading.Lock()
        self._conn_lock = threading.Lock()

        # Initialize database schema
        self._init_db()
        self._initialized = True

    def _init_db(self):
        """Initialize database with schema if not exists"""
        with self._conn_lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection (thread-safe)"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row  # Return rows as dicts
        return conn

    def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached result if not expired"""
        with self._cache_lock:
            if cache_key in self._cache:
                result, expiry = self._cache[cache_key]
                if time.time() < expiry:
                    return result
                else:
                    del self._cache[cache_key]
        return None

    def _set_cached(self, cache_key: str, result: Any):
        """Cache result with expiry timestamp"""
        with self._cache_lock:
            expiry = time.time() + self._cache_duration
            self._cache[cache_key] = (result, expiry)

    def _parse_node(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Parse node row into dict with properties"""
        node = {
            "node_id": row["node_id"],
            "node_type": row["node_type"],
            "person_id": row["person_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "properties": json.loads(row["properties"]),
        }
        return node

    # ========================================================================
    # High-Level Query Methods
    # ========================================================================

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Person node with basic user info.

        Args:
            user_id: User's node_id

        Returns:
            Person node dict or None if not found
        """
        cache_key = f"profile:{user_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM nodes WHERE node_id = ? AND node_type = ?",
            (user_id, NodeType.PERSON.value),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        result = self._parse_node(row)
        self._set_cached(cache_key, result)
        return result

    def get_health_context(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get recent HealthMetrics (last N days).

        Args:
            user_id: User's node_id
            days: Number of days to look back (default: 30)

        Returns:
            List of HealthMetric nodes
        """
        cache_key = f"health:{user_id}:{days}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        cutoff_date = (datetime.now() - timedelta(days=days)).date().isoformat()

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM nodes
            WHERE person_id = ? AND node_type = ?
            AND date(json_extract(properties, '$.date')) >= date(?)
            ORDER BY json_extract(properties, '$.date') DESC
        """,
            (user_id, NodeType.HEALTH_METRIC.value, cutoff_date),
        )
        rows = cursor.fetchall()
        conn.close()

        results = [self._parse_node(row) for row in rows]
        self._set_cached(cache_key, results)
        return results

    def get_active_goals(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all active Goal nodes for user.

        Args:
            user_id: User's node_id

        Returns:
            List of active Goal nodes
        """
        cache_key = f"goals:{user_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM nodes
            WHERE person_id = ? AND node_type = ?
            AND json_extract(properties, '$.active') = 1
            ORDER BY json_extract(properties, '$.deadline') ASC
        """,
            (user_id, NodeType.GOAL.value),
        )
        rows = cursor.fetchall()
        conn.close()

        results = [self._parse_node(row) for row in rows]
        self._set_cached(cache_key, results)
        return results

    def get_preferences(self, user_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get Preferences filtered by category.

        Args:
            user_id: User's node_id
            category: Preference category (e.g., "food", "exercise") or None for all

        Returns:
            List of Preference nodes
        """
        cache_key = f"prefs:{user_id}:{category}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        conn = self._get_connection()

        if category:
            cursor = conn.execute(
                """
                SELECT * FROM nodes
                WHERE person_id = ? AND node_type = ?
                AND json_extract(properties, '$.category') = ?
                ORDER BY json_extract(properties, '$.strength') DESC
            """,
                (user_id, NodeType.PREFERENCE.value, category),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM nodes
                WHERE person_id = ? AND node_type = ?
                ORDER BY json_extract(properties, '$.strength') DESC
            """,
                (user_id, NodeType.PREFERENCE.value),
            )

        rows = cursor.fetchall()
        conn.close()

        results = [self._parse_node(row) for row in rows]
        self._set_cached(cache_key, results)
        return results

    def get_routines(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all Routine nodes with adherence rates.

        Args:
            user_id: User's node_id

        Returns:
            List of Routine nodes
        """
        cache_key = f"routines:{user_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM nodes
            WHERE person_id = ? AND node_type = ?
            ORDER BY json_extract(properties, '$.adherence_rate') DESC
        """,
            (user_id, NodeType.ROUTINE.value),
        )
        rows = cursor.fetchall()
        conn.close()

        results = [self._parse_node(row) for row in rows]
        self._set_cached(cache_key, results)
        return results

    def get_relationships(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all Relationship nodes for user.

        Args:
            user_id: User's node_id

        Returns:
            List of Relationship nodes
        """
        cache_key = f"relationships:{user_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM nodes
            WHERE person_id = ? AND node_type = ?
            ORDER BY json_extract(properties, '$.closeness') DESC
        """,
            (user_id, NodeType.RELATIONSHIP.value),
        )
        rows = cursor.fetchall()
        conn.close()

        results = [self._parse_node(row) for row in rows]
        self._set_cached(cache_key, results)
        return results

    def query_memories(
        self,
        user_id: str,
        date_range: Optional[tuple[str, str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Memory nodes with date range and keyword filters.

        Args:
            user_id: User's node_id
            date_range: Optional (start_date, end_date) tuple in ISO format
            keywords: Optional list of keywords for FTS5 search

        Returns:
            List of Memory nodes
        """
        cache_key = f"memories:{user_id}:{date_range}:{keywords}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        conn = self._get_connection()

        # Base query
        query = "SELECT * FROM nodes WHERE person_id = ? AND node_type = ?"
        params = [user_id, NodeType.MEMORY.value]

        # Add date range filter
        if date_range:
            start_date, end_date = date_range
            query += " AND date(json_extract(properties, '$.date')) BETWEEN date(?) AND date(?)"
            params.extend([start_date, end_date])

        # Add keyword search (FTS5)
        if keywords:
            # Join with FTS table for keyword search
            query = """
                SELECT n.* FROM nodes n
                JOIN nodes_fts f ON n.node_id = f.node_id
                WHERE n.person_id = ? AND n.node_type = ?
                AND f.searchable_text MATCH ?
            """
            keyword_query = " OR ".join(keywords)
            params = [user_id, NodeType.MEMORY.value, keyword_query]

            if date_range:
                query += (
                    " AND date(json_extract(n.properties, '$.date')) BETWEEN date(?) AND date(?)"
                )
                params.extend([start_date, end_date])

        query += " ORDER BY json_extract(properties, '$.importance') DESC"

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        results = [self._parse_node(row) for row in rows]
        self._set_cached(cache_key, results)
        return results

    # ========================================================================
    # Write Operations (Add, Update, Delete)
    # ========================================================================

    def add_node(self, node_type: NodeType, person_id: str, properties: Dict[str, Any]) -> str:
        """
        Insert new node into graph.

        Args:
            node_type: Type of node to create
            person_id: User this node belongs to (empty string for Person nodes)
            properties: Node properties dict

        Returns:
            node_id of created node

        Raises:
            ValueError: If properties don't match schema
        """
        # Validate properties match schema
        if not validate_node_properties(node_type, properties):
            raise ValueError(f"Invalid properties for node type {node_type.value}")

        # Generate node_id
        import uuid

        node_id = f"node_{node_type.value}_{uuid.uuid4().hex[:8]}"

        now = datetime.utcnow().isoformat() + "Z"
        properties_json = json.dumps(properties)

        # For Person nodes, person_id is NULL initially, then updated to self-reference
        final_person_id = None if (node_type == NodeType.PERSON and not person_id) else person_id

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO nodes (node_id, node_type, person_id, created_at, updated_at, properties)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (node_id, node_type.value, final_person_id, now, now, properties_json),
        )

        # For Person nodes, update person_id to self-reference
        if node_type == NodeType.PERSON and not person_id:
            conn.execute(
                """
                UPDATE nodes SET person_id = ? WHERE node_id = ?
            """,
                (node_id, node_id),
            )

        conn.commit()
        conn.close()

        # Invalidate cache
        self._invalidate_cache()

        return node_id

    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        edge_type: EdgeType,
        properties: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Insert new edge between nodes.

        Args:
            from_node_id: Source node
            to_node_id: Target node
            edge_type: Type of edge
            properties: Optional edge properties

        Returns:
            edge_id of created edge
        """
        import uuid

        edge_id = f"edge_{edge_type.value}_{uuid.uuid4().hex[:8]}"

        now = datetime.utcnow().isoformat() + "Z"
        properties_json = json.dumps(properties) if properties else None

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO edges (edge_id, edge_type, from_node_id, to_node_id, created_at, properties)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (edge_id, edge_type.value, from_node_id, to_node_id, now, properties_json),
        )
        conn.commit()
        conn.close()

        return edge_id

    def update_node(self, node_id: str, properties: Dict[str, Any]):
        """
        Update existing node properties.

        Args:
            node_id: Node to update
            properties: New properties dict (replaces old properties)
        """
        now = datetime.utcnow().isoformat() + "Z"
        properties_json = json.dumps(properties)

        conn = self._get_connection()
        conn.execute(
            """
            UPDATE nodes SET properties = ?, updated_at = ?
            WHERE node_id = ?
        """,
            (properties_json, now, node_id),
        )
        conn.commit()
        conn.close()

        # Invalidate cache
        self._invalidate_cache()

    def delete_node(self, node_id: str):
        """
        Delete node and all its edges (cascade).

        Args:
            node_id: Node to delete
        """
        conn = self._get_connection()
        conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
        conn.commit()
        conn.close()

        # Invalidate cache
        self._invalidate_cache()

    def _invalidate_cache(self):
        """Clear all cached results"""
        with self._cache_lock:
            self._cache.clear()

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get KG statistics.

        Returns:
            Stats dict with node counts, edge counts, cache stats
        """
        conn = self._get_connection()

        # Node counts by type
        cursor = conn.execute("SELECT node_type, COUNT(*) as count FROM nodes GROUP BY node_type")
        node_counts = {row["node_type"]: row["count"] for row in cursor.fetchall()}

        # Edge counts by type
        cursor = conn.execute("SELECT edge_type, COUNT(*) as count FROM edges GROUP BY edge_type")
        edge_counts = {row["edge_type"]: row["count"] for row in cursor.fetchall()}

        # Total counts
        cursor = conn.execute("SELECT COUNT(*) as count FROM nodes")
        total_nodes = cursor.fetchone()["count"]

        cursor = conn.execute("SELECT COUNT(*) as count FROM edges")
        total_edges = cursor.fetchone()["count"]

        conn.close()

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "node_counts": node_counts,
            "edge_counts": edge_counts,
            "cache_size": len(self._cache),
            "db_path": self.db_path,
        }

    def clear_all_data(self):
        """Clear all nodes and edges (for testing only)"""
        conn = self._get_connection()
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM nodes")
        conn.commit()
        conn.close()
        self._invalidate_cache()

    def close(self):
        """No-op close for API compatibility.

        The UserKG maintains no persistent open connection; connections are
        short-lived per call. This method exists to satisfy callers that expect
        a `.close()` on shutdown (e.g., SystemCoordinator).
        """
        # Nothing to close; keep method for interface compatibility
        return None


# Factory function for easy import
def get_user_kg(db_path: Optional[str] = None) -> UserKG:
    """
    Get UserKG singleton instance.

    Args:
        db_path: Optional database path

    Returns:
        UserKG instance
    """
    return UserKG(db_path)
