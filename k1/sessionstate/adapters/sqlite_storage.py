"""
SQLiteStorageAdapter - LOCAL COLD Storage Implementation
==========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.1 Define Storage Port
ISSUE: 3.1.2

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Offline-safe local archive using K1 SQLite database.
    This is the LOCAL COLD tier - always available, no network dependency.

EDGE-FIRST DESIGN:
    - PRIMARY storage (not fallback)
    - Always available (no network dependency)
    - SessionState MUST work fully offline with this

BRIDGE ALIGNMENT:
    - archive() maps to Bridge command topics:
      - session.checkpoint -> st_session_checkpoints
      - beliefs.archive -> st_beliefs_archive
      - history.archive -> st_history_archive
    - Data is FlatBuffer bytes for envelope compatibility

TABLES:
    st_session_checkpoints - Full session snapshots
    st_beliefs_archive     - Evicted beliefs
    st_history_archive     - Evicted history
    st_narrative_archive   - Evicted narrative threads

LOCATION:
    Default: ~/.familyos/k1/sessionstate.db
    Configurable via constructor

SLA:
    <50ms for restore operations (P95)

==============================================================================
CLASS: SQLiteStorageAdapter
==============================================================================
"""

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import SessionStateConfig
from ..ports.storage import ArchiveEntry, ArchiveResult, IStoragePort, RestoreResult

# Default database path (config: sessionstate.storage.default_db_path)
DEFAULT_DB_PATH = Path.home() / ".familyos" / "k1" / "sessionstate.db"

# SLA threshold for warnings (config: sessionstate.storage.sla_storage_ms)
SLA_MS = 50.0

# Logger
logger = logging.getLogger(__name__)

# Table mapping
TABLE_MAPPING = {
    "beliefs_active": "st_beliefs_archive",
    "beliefs_history": "st_beliefs_archive",
    "history_active": "st_history_archive",
    "history_recent": "st_history_archive",
    "narrative_active": "st_narrative_archive",
    "checkpoint": "st_session_checkpoints",
}

# All tables for iteration
ALL_TABLES = [
    "st_session_checkpoints",
    "st_beliefs_archive",
    "st_history_archive",
    "st_narrative_archive",
]


class SQLiteStorageAdapter(IStoragePort):
    """
    SQLite-based storage adapter for LOCAL COLD tier.

    ALWAYS AVAILABLE - no network dependency.

    Attributes:
        _db_path: Path to SQLite database file
        _conn: SQLite connection (WAL mode)

    Example:
        adapter = SQLiteStorageAdapter()

        # Archive evicted data
        result = adapter.archive(
            section="telemetry",
            data=flatbuffer_bytes,
            metadata={"session_id": "123", "reason": "eviction"},
        )

        # Restore for reconstruction
        result = adapter.restore(
            section="telemetry",
            filters={"session_id": "123"},
        )
    """

    def __init__(
        self, db_path: Optional[Path | str] = None, config: Optional[SessionStateConfig] = None
    ) -> None:
        """
        Initialize SQLiteStorageAdapter.

        Args:
            db_path: Path to SQLite database (Path or str).
                     Default: ~/.familyos/k1/sessionstate.db
            config: Optional SessionStateConfig (defaults used if None)
        """
        self._ss_cfg = config or SessionStateConfig()
        if db_path is None:
            self._db_path = Path(self._ss_cfg.storage.default_db_path).expanduser()
        elif isinstance(db_path, str):
            self._db_path = Path(db_path)
        else:
            self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

        logger.info("SQLiteStorageAdapter initialized (path=%s)", self._db_path)

    def _init_schema(self) -> None:
        """Initialize database schema."""
        cursor = self._conn.cursor()

        # Session checkpoints table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_session_checkpoints (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL DEFAULT 'checkpoint',
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                metadata TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_checkpoints_session
            ON st_session_checkpoints(session_id)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_checkpoints_created
            ON st_session_checkpoints(created_at_ms)
        """
        )

        # Beliefs archive table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_beliefs_archive (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                turn_id TEXT,
                metadata TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_session
            ON st_beliefs_archive(session_id)
        """
        )

        # History archive table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_history_archive (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                turn_range TEXT,
                metadata TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_history_session
            ON st_history_archive(session_id)
        """
        )

        # Narrative archive table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_narrative_archive (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                thread_id TEXT,
                metadata TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_narrative_session
            ON st_narrative_archive(session_id)
        """
        )

        self._conn.commit()

    @property
    def is_available(self) -> bool:
        """
        Check if storage is available.

        Returns:
            bool: Always True (local SQLite always available)
        """
        return True

    @property
    def storage_type(self) -> str:
        """
        Get storage type identifier.

        Returns:
            str: 'local'
        """
        return "local"

    def archive(
        self,
        section: str,
        data: bytes,
        metadata: Dict[str, Any],
    ) -> ArchiveResult:
        """
        Archive data to LOCAL COLD.

        Args:
            section: Section name (determines table)
            data: FlatBuffer-serialized data
            metadata: Must include 'session_id'

        Returns:
            ArchiveResult: Success/failure with archive_id
        """
        start = time.perf_counter()
        archive_id = str(uuid.uuid4())

        session_id = metadata.get("session_id", "")
        if not session_id:
            return ArchiveResult(
                success=False,
                archive_id="",
                size_bytes=0,
                duration_ms=0.0,
                error="session_id required in metadata",
            )

        table = self._get_table_for_section(section)
        if not table:
            return ArchiveResult(
                success=False,
                archive_id="",
                size_bytes=0,
                duration_ms=0.0,
                error=f"Unknown section: {section}",
            )

        try:
            # Get extra fields based on table
            turn_id = metadata.get("turn_id")
            turn_range = metadata.get("turn_range")
            thread_id = metadata.get("thread_id")

            if table == "st_beliefs_archive":
                self._conn.execute(
                    """INSERT INTO st_beliefs_archive
                    (id, session_id, section, data, size_bytes, created_at_ms, turn_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        len(data),
                        int(time.time() * 1000),
                        turn_id,
                        json.dumps(metadata),
                    ),
                )
            elif table == "st_history_archive":
                self._conn.execute(
                    """INSERT INTO st_history_archive
                    (id, session_id, section, data, size_bytes, created_at_ms, turn_range, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        len(data),
                        int(time.time() * 1000),
                        turn_range,
                        json.dumps(metadata),
                    ),
                )
            elif table == "st_narrative_archive":
                self._conn.execute(
                    """INSERT INTO st_narrative_archive
                    (id, session_id, section, data, size_bytes, created_at_ms, thread_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        len(data),
                        int(time.time() * 1000),
                        thread_id,
                        json.dumps(metadata),
                    ),
                )
            else:  # st_session_checkpoints
                self._conn.execute(
                    """INSERT INTO st_session_checkpoints
                    (id, session_id, section, data, size_bytes, created_at_ms, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        len(data),
                        int(time.time() * 1000),
                        json.dumps(metadata),
                    ),
                )

            self._conn.commit()

            duration_ms = (time.perf_counter() - start) * 1000
            if duration_ms > self._ss_cfg.storage.sla_storage_ms:
                logger.warning(f"Archive SLA breach: {duration_ms:.1f}ms (section={section})")

            return ArchiveResult(
                success=True,
                archive_id=archive_id,
                size_bytes=len(data),
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"Archive failed: {e}")
            return ArchiveResult(
                success=False,
                archive_id="",
                size_bytes=0,
                duration_ms=duration_ms,
                error=str(e),
            )

    def restore(
        self,
        section: str,
        filters: Dict[str, Any],
    ) -> RestoreResult:
        """
        Restore data from LOCAL COLD.

        Args:
            section: Section name
            filters: Must include 'session_id'

        Returns:
            RestoreResult: Data if found, error if not
        """
        start = time.perf_counter()

        session_id = filters.get("session_id", "")
        if not session_id:
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=0.0,
                error="session_id required in filters",
            )

        table = self._get_table_for_section(section)
        if not table:
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=0.0,
                error=f"Unknown section: {section}",
            )

        try:
            # Check for specific archive_id first
            archive_id = filters.get("archive_id")
            if archive_id:
                cursor = self._conn.execute(
                    f"SELECT id, data, size_bytes FROM {table} WHERE id = ?",
                    (archive_id,),
                )
            else:
                # Get most recent for session + section
                cursor = self._conn.execute(
                    f"""SELECT id, data, size_bytes FROM {table}
                    WHERE session_id = ? AND section = ?
                    ORDER BY created_at_ms DESC LIMIT 1""",
                    (session_id, section),
                )

            row = cursor.fetchone()
            duration_ms = (time.perf_counter() - start) * 1000

            if duration_ms > self._ss_cfg.storage.sla_storage_ms:
                logger.warning(f"Restore SLA breach: {duration_ms:.1f}ms (section={section})")

            if row:
                return RestoreResult(
                    success=True,
                    data=row[1],
                    archive_id=row[0],
                    size_bytes=row[2],
                    duration_ms=duration_ms,
                )
            else:
                return RestoreResult(
                    success=False,
                    data=None,
                    archive_id="",
                    size_bytes=0,
                    duration_ms=duration_ms,
                    error=f"No archive found for session={session_id}, section={section}",
                )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"Restore failed: {e}")
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=duration_ms,
                error=str(e),
            )

    def list_archives(
        self,
        session_id: str,
    ) -> List[ArchiveEntry]:
        """
        List all archives for a session.

        Args:
            session_id: Session to list

        Returns:
            List[ArchiveEntry]: Archive metadata (not data)
        """
        entries: List[ArchiveEntry] = []

        for table in ALL_TABLES:
            try:
                cursor = self._conn.execute(
                    f"""SELECT id, session_id, section, size_bytes, created_at_ms, metadata
                    FROM {table} WHERE session_id = ?
                    ORDER BY created_at_ms DESC""",
                    (session_id,),
                )
                for row in cursor.fetchall():
                    metadata = {}
                    if row[5]:
                        try:
                            metadata = json.loads(row[5])
                        except json.JSONDecodeError:
                            metadata = {}

                    entries.append(
                        ArchiveEntry(
                            archive_id=row[0],
                            session_id=row[1],
                            section=row[2],
                            size_bytes=row[3],
                            created_at_ms=row[4],
                            metadata=metadata,
                        )
                    )
            except Exception as e:
                logger.error(f"Error listing archives from {table}: {e}")

        return entries

    def delete(self, archive_id: str) -> bool:
        """
        Delete an archive entry.

        Args:
            archive_id: Archive to delete

        Returns:
            bool: True if deleted
        """
        for table in ALL_TABLES:
            try:
                cursor = self._conn.execute(
                    f"DELETE FROM {table} WHERE id = ?",
                    (archive_id,),
                )
                self._conn.commit()
                if cursor.rowcount > 0:
                    return True
            except Exception as e:
                logger.error(f"Error deleting from {table}: {e}")

        return False

    def _get_table_for_section(self, section: str) -> Optional[str]:
        """
        Map section name to table name.

        Args:
            section: Section name

        Returns:
            str: Table name or None if unknown
        """
        # Direct mapping
        if section in TABLE_MAPPING:
            return TABLE_MAPPING[section]

        # Prefix matching for flexibility
        if section.startswith("beliefs"):
            return "st_beliefs_archive"
        if section.startswith("history"):
            return "st_history_archive"
        if section.startswith("narrative"):
            return "st_narrative_archive"

        # Default to checkpoints for unknown sections
        return "st_session_checkpoints"

    def close(self) -> None:
        """
        Close database connection.

        Call on shutdown.
        """
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore

    def vacuum(self) -> None:
        """Run VACUUM to reclaim space."""
        if self._conn:
            self._conn.execute("VACUUM")

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        return f"SQLiteStorageAdapter(db_path={self._db_path})"
        return f"SQLiteStorageAdapter(db_path={self._db_path})"
