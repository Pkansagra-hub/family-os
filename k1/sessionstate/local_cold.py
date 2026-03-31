"""
LocalColdArchive - Offline-Safe Local Archive (K1 SQLite)
==========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.7

ADRs:
- ADR-0020: Multi-Tier Storage Architecture
- ADR-NEW: LOCAL COLD Tier (K1 SQLite) - to be created

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Offline-safe local archive using K1 SQLite database.
    This is the LOCAL COLD tier - always available, no network dependency.

EDGE-FIRST DESIGN:
    - LOCAL COLD is the PRIMARY persistence layer
    - K0 sync is OPTIONAL enhancement for cross-device
    - SessionState MUST work fully offline

TABLES:
    st_session_checkpoints - Full session snapshots
    st_beliefs_archive     - Evicted beliefs
    st_history_archive     - Evicted history
    st_narrative_archive   - Evicted narrative threads

LOCATION:
    Default: ~/.familyos/k1/sessionstate.db
    Configurable via environment or factory

==============================================================================
CLASS: LocalColdArchive
==============================================================================
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from poc.k1_poc.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ArchiveEntry:
    """
    Metadata for an archived item.

    Attributes:
        archive_id: Unique archive identifier
        session_id: Session this belongs to
        section: Section name
        size_bytes: Size of archived data
        created_at_ms: Archive timestamp
        metadata: Additional metadata (e.g., turn_id, reason)
    """

    archive_id: str
    session_id: str
    section: str
    size_bytes: int
    created_at_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchiveResult:
    """
    Result of an archive operation.

    Attributes:
        success: Whether archive succeeded
        archive_id: ID of created archive entry
        size_bytes: Size of archived data
        duration_ms: Time taken
        error: Error message if failed
    """

    success: bool
    archive_id: str
    size_bytes: int
    duration_ms: float
    error: Optional[str] = None


@dataclass
class RestoreResult:
    """
    Result of a restore operation.

    Attributes:
        success: Whether restore succeeded
        data: Restored data (bytes)
        archive_id: ID of restored archive
        size_bytes: Size of restored data
        duration_ms: Time taken
        error: Error message if failed
    """

    success: bool
    data: Optional[bytes]
    archive_id: str
    size_bytes: int
    duration_ms: float
    error: Optional[str] = None


# Default database path (config: sessionstate.storage.default_db_path)
DEFAULT_DB_PATH = Path.home() / ".familyos" / "k1" / "sessionstate.db"

# SLA threshold for restore operations (config: sessionstate.storage.sla_restore_ms)
SLA_RESTORE_MS = 50.0

# Section to table mapping
SECTION_TABLE_MAP: Dict[str, str] = {
    "beliefs_active": "st_beliefs_archive",
    "beliefs_history": "st_beliefs_archive",
    "history_active": "st_history_archive",
    "history_recent": "st_history_archive",
    "narrative_active": "st_narrative_archive",
    "telemetry": "st_telemetry_archive",  # WARM eviction target
    "persona": "st_persona_archive",  # WARM eviction target
    "checkpoint": "st_session_checkpoints",
}

# All archive tables (for queries across tables)
ARCHIVE_TABLES = [
    "st_session_checkpoints",
    "st_beliefs_archive",
    "st_history_archive",
    "st_narrative_archive",
    "st_telemetry_archive",
    "st_persona_archive",
]


class LocalColdArchive:
    """
    Manages offline-safe local archive using K1 SQLite.

    This is the LOCAL COLD tier - always available for:
    - Evicted WARM data
    - Session checkpoints
    - Offline operation

    Thread Safety:
        - Uses WAL mode for concurrent read access
        - One writer at a time (SQLite handles locking)
        - check_same_thread=False allows multi-thread access

    Performance:
        - archive(): <10ms typical
        - restore(): <50ms SLA target
        - list_archives(): O(n) where n = archives for session

    Attributes:
        _db_path: Path to SQLite database
        _conn: SQLite connection

    Example:
        archive = LocalColdArchive()

        # Archive evicted data
        result = archive.archive(
            section="telemetry",
            data=serialized_telemetry,
            session_id="session-123",
            metadata={"reason": "eviction", "priority": 1},
        )

        # Restore for reconstruction
        result = archive.restore(
            section="telemetry",
            session_id="session-123",
        )
    """

    __slots__ = ("_db_path", "_conn", "_closed")

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        Initialize LocalColdArchive.

        Args:
            db_path: Path to SQLite database.
                     Default: ~/.familyos/k1/sessionstate.db

        Actions:
            1. Create directory if needed
            2. Open/create SQLite database
            3. Enable WAL mode for concurrency
            4. Initialize schema if needed
        """
        if db_path is not None:
            self._db_path = db_path
        else:
            cfg_path = get_config().sessionstate.storage.default_db_path
            self._db_path = Path(cfg_path).expanduser()
        self._closed = False

        # Create parent directory if needed
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Open SQLite connection with WAL mode
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=30.0,  # Wait up to 30s for locks
        )
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")  # Faster with WAL
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self._conn.execute("PRAGMA temp_store=MEMORY")

        # Initialize schema
        self._init_schema()

        logger.info(
            "LocalColdArchive initialized (path=%s, tables=%d)",
            self._db_path,
            len(ARCHIVE_TABLES),
        )

    def _init_schema(self) -> None:
        """
        Initialize database schema.

        Creates tables and indexes if they don't exist.
        """
        cursor = self._conn.cursor()

        # st_session_checkpoints - Full session snapshots
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_session_checkpoints (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
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

        # st_beliefs_archive - Evicted beliefs
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
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_section
            ON st_beliefs_archive(session_id, section)
        """
        )

        # st_history_archive - Evicted history
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
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_history_section
            ON st_history_archive(session_id, section)
        """
        )

        # st_narrative_archive - Evicted narrative threads
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
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_narrative_section
            ON st_narrative_archive(session_id, section)
        """
        )

        # st_telemetry_archive - Evicted telemetry data (WARM tier, priority 1)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_telemetry_archive (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                metadata TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_telemetry_session
            ON st_telemetry_archive(session_id)
        """
        )

        # st_persona_archive - Evicted persona data (WARM tier, priority 10)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS st_persona_archive (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                data BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                metadata TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_persona_session
            ON st_persona_archive(session_id)
        """
        )

        self._conn.commit()
        logger.debug("LocalColdArchive schema initialized")

    def _get_table_for_section(self, section: str) -> str:
        """
        Map section name to table name.

        Args:
            section: Section name

        Returns:
            str: Table name

        Raises:
            ValueError: If section not recognized
        """
        if section in SECTION_TABLE_MAP:
            return SECTION_TABLE_MAP[section]

        # Fallback mappings based on prefix
        if section.startswith("beliefs"):
            return "st_beliefs_archive"
        if section.startswith("history"):
            return "st_history_archive"
        if section.startswith("narrative"):
            return "st_narrative_archive"

        raise ValueError(f"Unknown section: {section}")

    def _elapsed_ms(self, start_time: float) -> float:
        """Calculate elapsed time in milliseconds."""
        return (time.perf_counter() - start_time) * 1000

    # =========================================================================
    # ARCHIVE OPERATIONS
    # =========================================================================

    def archive(
        self,
        section: str,
        data: bytes,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArchiveResult:
        """
        Archive data to LOCAL COLD.

        Args:
            section: Section name (determines table)
            data: FlatBuffer-serialized data
            session_id: Session this belongs to
            metadata: Optional metadata (reason, turn_id, etc.)

        Returns:
            ArchiveResult: Success/failure with archive_id

        Table mapping:
            - beliefs_active, beliefs_history -> st_beliefs_archive
            - history_active, history_recent -> st_history_archive
            - narrative_active -> st_narrative_archive
            - checkpoint -> st_session_checkpoints
        """
        start_time = time.perf_counter()
        archive_id = str(uuid.uuid4())
        metadata = metadata or {}

        try:
            table = self._get_table_for_section(section)
            created_at_ms = int(time.time() * 1000)
            size_bytes = len(data)
            metadata_json = json.dumps(metadata) if metadata else None

            if table == "st_session_checkpoints":
                self._conn.execute(
                    """
                    INSERT INTO st_session_checkpoints
                    (id, session_id, data, size_bytes, created_at_ms, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (archive_id, session_id, data, size_bytes, created_at_ms, metadata_json),
                )
            elif table == "st_beliefs_archive":
                turn_id = metadata.get("turn_id")
                self._conn.execute(
                    """
                    INSERT INTO st_beliefs_archive
                    (id, session_id, section, data, size_bytes, created_at_ms, turn_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        size_bytes,
                        created_at_ms,
                        turn_id,
                        metadata_json,
                    ),
                )
            elif table == "st_history_archive":
                turn_range = metadata.get("turn_range")
                self._conn.execute(
                    """
                    INSERT INTO st_history_archive
                    (id, session_id, section, data, size_bytes, created_at_ms, turn_range, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        size_bytes,
                        created_at_ms,
                        turn_range,
                        metadata_json,
                    ),
                )
            elif table == "st_narrative_archive":
                thread_id = metadata.get("thread_id")
                self._conn.execute(
                    """
                    INSERT INTO st_narrative_archive
                    (id, session_id, section, data, size_bytes, created_at_ms, thread_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        size_bytes,
                        created_at_ms,
                        thread_id,
                        metadata_json,
                    ),
                )
            elif table in ("st_telemetry_archive", "st_persona_archive"):
                # Generic archive for telemetry and persona (WARM eviction targets)
                self._conn.execute(
                    f"""
                    INSERT INTO {table}
                    (id, session_id, section, data, size_bytes, created_at_ms, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_id,
                        session_id,
                        section,
                        data,
                        size_bytes,
                        created_at_ms,
                        metadata_json,
                    ),
                )
            else:
                raise ValueError(f"Unknown table: {table}")

            self._conn.commit()
            duration_ms = self._elapsed_ms(start_time)

            logger.debug(
                "Archived %s for session %s: %d bytes in %.2fms",
                section,
                session_id[:8],
                size_bytes,
                duration_ms,
            )

            return ArchiveResult(
                success=True,
                archive_id=archive_id,
                size_bytes=size_bytes,
                duration_ms=duration_ms,
            )

        except ValueError as e:
            return ArchiveResult(
                success=False,
                archive_id="",
                size_bytes=0,
                duration_ms=self._elapsed_ms(start_time),
                error=str(e),
            )
        except sqlite3.Error as e:
            logger.error(
                "Archive failed for %s session %s: %s",
                section,
                session_id[:8],
                str(e),
            )
            return ArchiveResult(
                success=False,
                archive_id="",
                size_bytes=0,
                duration_ms=self._elapsed_ms(start_time),
                error=f"Database error: {e}",
            )

    # =========================================================================
    # RESTORE OPERATIONS
    # =========================================================================

    def restore(
        self,
        section: str,
        session_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> RestoreResult:
        """
        Restore data from LOCAL COLD.

        Args:
            section: Section name
            session_id: Session to restore
            filters: Optional filters (archive_id, after_ms, before_ms)

        Returns:
            RestoreResult: Data if found, error if not

        SLA:
            <50ms for most restores
        """
        start_time = time.perf_counter()
        filters = filters or {}

        try:
            table = self._get_table_for_section(section)

            # Build query based on table type
            if table == "st_session_checkpoints":
                query = """
                    SELECT id, data, size_bytes FROM st_session_checkpoints
                    WHERE session_id = ?
                    ORDER BY created_at_ms DESC LIMIT 1
                """
                params: tuple = (session_id,)
            else:
                # For other tables, also filter by section
                query = f"""
                    SELECT id, data, size_bytes FROM {table}
                    WHERE session_id = ? AND section = ?
                    ORDER BY created_at_ms DESC LIMIT 1
                """
                params = (session_id, section)

            # Apply optional filters
            if "archive_id" in filters:
                query = f"""
                    SELECT id, data, size_bytes FROM {table}
                    WHERE id = ?
                """
                params = (filters["archive_id"],)

            cursor = self._conn.execute(query, params)
            row = cursor.fetchone()

            duration_ms = self._elapsed_ms(start_time)

            sla_ms = get_config().sessionstate.storage.sla_restore_ms
            if duration_ms > sla_ms:
                logger.warning(
                    "Restore SLA breach: %s for session %s took %.2fms (>%.0fms)",
                    section,
                    session_id[:8],
                    duration_ms,
                    sla_ms,
                )

            if row:
                return RestoreResult(
                    success=True,
                    data=row["data"],
                    archive_id=row["id"],
                    size_bytes=row["size_bytes"],
                    duration_ms=duration_ms,
                )
            else:
                return RestoreResult(
                    success=False,
                    data=None,
                    archive_id="",
                    size_bytes=0,
                    duration_ms=duration_ms,
                    error=f"No archive found for {section} in session {session_id}",
                )

        except ValueError as e:
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=self._elapsed_ms(start_time),
                error=str(e),
            )
        except sqlite3.Error as e:
            logger.error(
                "Restore failed for %s session %s: %s",
                section,
                session_id[:8],
                str(e),
            )
            return RestoreResult(
                success=False,
                data=None,
                archive_id="",
                size_bytes=0,
                duration_ms=self._elapsed_ms(start_time),
                error=f"Database error: {e}",
            )

    def restore_all(
        self,
        section: str,
        session_id: str,
        limit: int = 100,
    ) -> List[RestoreResult]:
        """
        Restore all archives for a section (newest first).

        Args:
            section: Section name
            session_id: Session to restore
            limit: Maximum entries to return

        Returns:
            List[RestoreResult]: All matching archives
        """
        start_time = time.perf_counter()
        results: List[RestoreResult] = []

        try:
            table = self._get_table_for_section(section)

            if table == "st_session_checkpoints":
                query = """
                    SELECT id, data, size_bytes FROM st_session_checkpoints
                    WHERE session_id = ?
                    ORDER BY created_at_ms DESC LIMIT ?
                """
                params = (session_id, limit)
            else:
                query = f"""
                    SELECT id, data, size_bytes FROM {table}
                    WHERE session_id = ? AND section = ?
                    ORDER BY created_at_ms DESC LIMIT ?
                """
                params = (session_id, section, limit)

            cursor = self._conn.execute(query, params)

            for row in cursor:
                results.append(
                    RestoreResult(
                        success=True,
                        data=row["data"],
                        archive_id=row["id"],
                        size_bytes=row["size_bytes"],
                        duration_ms=self._elapsed_ms(start_time),
                    )
                )

            return results

        except (ValueError, sqlite3.Error) as e:
            logger.error("restore_all failed: %s", str(e))
            return results

    # =========================================================================
    # LIST / QUERY OPERATIONS
    # =========================================================================

    def list_archives(
        self,
        session_id: str,
        section: Optional[str] = None,
    ) -> List[ArchiveEntry]:
        """
        List all archives for a session.

        Args:
            session_id: Session to list
            section: Optional section filter

        Returns:
            List[ArchiveEntry]: Archive metadata (not data)
        """
        entries: List[ArchiveEntry] = []

        try:
            # Query each table
            for table in ARCHIVE_TABLES:
                if table == "st_session_checkpoints":
                    # Checkpoints don't have a section column
                    if section and section != "checkpoint":
                        continue
                    query = """
                        SELECT id, session_id, 'checkpoint' as section,
                               size_bytes, created_at_ms, metadata
                        FROM st_session_checkpoints
                        WHERE session_id = ?
                        ORDER BY created_at_ms DESC
                    """
                    params: tuple = (session_id,)
                else:
                    if section:
                        query = f"""
                            SELECT id, session_id, section,
                                   size_bytes, created_at_ms, metadata
                            FROM {table}
                            WHERE session_id = ? AND section = ?
                            ORDER BY created_at_ms DESC
                        """
                        params = (session_id, section)
                    else:
                        query = f"""
                            SELECT id, session_id, section,
                                   size_bytes, created_at_ms, metadata
                            FROM {table}
                            WHERE session_id = ?
                            ORDER BY created_at_ms DESC
                        """
                        params = (session_id,)

                cursor = self._conn.execute(query, params)

                for row in cursor:
                    metadata = {}
                    if row["metadata"]:
                        try:
                            metadata = json.loads(row["metadata"])
                        except json.JSONDecodeError:
                            pass

                    entries.append(
                        ArchiveEntry(
                            archive_id=row["id"],
                            session_id=row["session_id"],
                            section=row["section"],
                            size_bytes=row["size_bytes"],
                            created_at_ms=row["created_at_ms"],
                            metadata=metadata,
                        )
                    )

            return entries

        except sqlite3.Error as e:
            logger.error("list_archives failed for session %s: %s", session_id[:8], str(e))
            return entries

    def has_session(self, session_id: str) -> bool:
        """
        Check if a session has any archived data.

        Args:
            session_id: Session to check

        Returns:
            bool: True if any archives exist
        """
        try:
            for table in ARCHIVE_TABLES:
                cursor = self._conn.execute(
                    f"SELECT 1 FROM {table} WHERE session_id = ? LIMIT 1",
                    (session_id,),
                )
                if cursor.fetchone():
                    return True
            return False
        except sqlite3.Error:
            return False

    # =========================================================================
    # DELETE OPERATIONS
    # =========================================================================

    def delete(self, archive_id: str) -> bool:
        """
        Delete an archive entry.

        Args:
            archive_id: Archive to delete

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            for table in ARCHIVE_TABLES:
                cursor = self._conn.execute(
                    f"DELETE FROM {table} WHERE id = ?",
                    (archive_id,),
                )
                if cursor.rowcount > 0:
                    self._conn.commit()
                    logger.debug("Deleted archive %s from %s", archive_id[:8], table)
                    return True
            return False
        except sqlite3.Error as e:
            logger.error("Delete failed for archive %s: %s", archive_id[:8], str(e))
            return False

    def delete_session(self, session_id: str) -> int:
        """
        Delete all archives for a session.

        Args:
            session_id: Session to delete

        Returns:
            int: Number of entries deleted
        """
        total_deleted = 0
        try:
            for table in ARCHIVE_TABLES:
                cursor = self._conn.execute(
                    f"DELETE FROM {table} WHERE session_id = ?",
                    (session_id,),
                )
                total_deleted += cursor.rowcount

            self._conn.commit()
            logger.info("Deleted %d archives for session %s", total_deleted, session_id[:8])
            return total_deleted

        except sqlite3.Error as e:
            logger.error("delete_session failed for %s: %s", session_id[:8], str(e))
            return total_deleted

    # =========================================================================
    # CHECKPOINT OPERATIONS
    # =========================================================================

    def checkpoint(
        self,
        session_id: str,
        data: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArchiveResult:
        """
        Create a full session checkpoint.

        Args:
            session_id: Session to checkpoint
            data: Full session data (FlatBuffer-serialized)
            metadata: Optional checkpoint metadata

        Returns:
            ArchiveResult: Success/failure with checkpoint_id

        Behavior:
            - Creates new checkpoint entry
            - Does NOT delete old checkpoints (for history)
            - Use prune_checkpoints() to clean old ones
        """
        return self.archive(
            section="checkpoint",
            data=data,
            session_id=session_id,
            metadata=metadata,
        )

    def restore_checkpoint(
        self,
        session_id: str,
        checkpoint_id: Optional[str] = None,
    ) -> RestoreResult:
        """
        Restore from checkpoint.

        Args:
            session_id: Session to restore
            checkpoint_id: Specific checkpoint (None = latest)

        Returns:
            RestoreResult: Full session data
        """
        filters = {}
        if checkpoint_id:
            filters["archive_id"] = checkpoint_id

        return self.restore(
            section="checkpoint",
            session_id=session_id,
            filters=filters,
        )

    def list_checkpoints(self, session_id: str) -> List[ArchiveEntry]:
        """
        List all checkpoints for a session.

        Args:
            session_id: Session to list

        Returns:
            List[ArchiveEntry]: Checkpoint metadata (newest first)
        """
        return self.list_archives(session_id=session_id, section="checkpoint")

    def prune_checkpoints(
        self,
        session_id: str,
        keep_count: int = 5,
    ) -> int:
        """
        Remove old checkpoints, keeping most recent.

        Args:
            session_id: Session to prune
            keep_count: Number of checkpoints to keep

        Returns:
            int: Number of checkpoints deleted
        """
        try:
            # Get all checkpoint IDs ordered by created_at_ms DESC
            cursor = self._conn.execute(
                """
                SELECT id FROM st_session_checkpoints
                WHERE session_id = ?
                ORDER BY created_at_ms DESC
                """,
                (session_id,),
            )

            all_ids = [row["id"] for row in cursor]

            if len(all_ids) <= keep_count:
                return 0

            # Delete older checkpoints
            ids_to_delete = all_ids[keep_count:]
            placeholders = ",".join("?" for _ in ids_to_delete)

            cursor = self._conn.execute(
                f"DELETE FROM st_session_checkpoints WHERE id IN ({placeholders})",
                tuple(ids_to_delete),
            )

            deleted = cursor.rowcount
            self._conn.commit()

            logger.info(
                "Pruned %d checkpoints for session %s, kept %d",
                deleted,
                session_id[:8],
                keep_count,
            )
            return deleted

        except sqlite3.Error as e:
            logger.error("prune_checkpoints failed for %s: %s", session_id[:8], str(e))
            return 0

    # =========================================================================
    # SIZE / STATS OPERATIONS
    # =========================================================================

    def get_total_size(self, session_id: Optional[str] = None) -> int:
        """
        Get total archive size.

        Args:
            session_id: Optional session filter

        Returns:
            int: Total bytes archived
        """
        total = 0
        try:
            for table in ARCHIVE_TABLES:
                if session_id:
                    cursor = self._conn.execute(
                        f"SELECT COALESCE(SUM(size_bytes), 0) as total FROM {table} WHERE session_id = ?",
                        (session_id,),
                    )
                else:
                    cursor = self._conn.execute(
                        f"SELECT COALESCE(SUM(size_bytes), 0) as total FROM {table}"
                    )
                row = cursor.fetchone()
                if row:
                    total += row["total"]
            return total
        except sqlite3.Error as e:
            logger.error("get_total_size failed: %s", str(e))
            return total

    def get_archive_count(self, session_id: Optional[str] = None) -> int:
        """
        Get total archive count.

        Args:
            session_id: Optional session filter

        Returns:
            int: Number of archive entries
        """
        total = 0
        try:
            for table in ARCHIVE_TABLES:
                if session_id:
                    cursor = self._conn.execute(
                        f"SELECT COUNT(*) as cnt FROM {table} WHERE session_id = ?",
                        (session_id,),
                    )
                else:
                    cursor = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                row = cursor.fetchone()
                if row:
                    total += row["cnt"]
            return total
        except sqlite3.Error as e:
            logger.error("get_archive_count failed: %s", str(e))
            return total

    def get_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get archive statistics.

        Args:
            session_id: Optional session filter

        Returns:
            Dict with total_size_bytes, archive_count, tables breakdown
        """
        stats: Dict[str, Any] = {
            "total_size_bytes": 0,
            "archive_count": 0,
            "tables": {},
        }

        try:
            for table in ARCHIVE_TABLES:
                if session_id:
                    cursor = self._conn.execute(
                        f"""
                        SELECT COUNT(*) as cnt, COALESCE(SUM(size_bytes), 0) as size
                        FROM {table} WHERE session_id = ?
                        """,
                        (session_id,),
                    )
                else:
                    cursor = self._conn.execute(
                        f"""
                        SELECT COUNT(*) as cnt, COALESCE(SUM(size_bytes), 0) as size
                        FROM {table}
                        """
                    )
                row = cursor.fetchone()
                if row:
                    stats["tables"][table] = {
                        "count": row["cnt"],
                        "size_bytes": row["size"],
                    }
                    stats["total_size_bytes"] += row["size"]
                    stats["archive_count"] += row["cnt"]

            return stats

        except sqlite3.Error as e:
            logger.error("get_stats failed: %s", str(e))
            return stats

    # =========================================================================
    # MAINTENANCE OPERATIONS
    # =========================================================================

    def vacuum(self) -> None:
        """
        Vacuum the SQLite database to reclaim space.

        Call after deleting significant data.
        """
        try:
            self._conn.execute("VACUUM")
            logger.debug("Database vacuumed: %s", self._db_path)
        except sqlite3.Error as e:
            logger.error("Vacuum failed: %s", str(e))

    def close(self) -> None:
        """
        Close database connection.

        Call on shutdown.
        """
        if not self._closed and self._conn:
            self._conn.close()
            self._closed = True
            logger.debug("LocalColdArchive closed: %s", self._db_path)

    def __enter__(self) -> "LocalColdArchive":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    @property
    def db_path(self) -> Path:
        """Get the database path."""
        return self._db_path

    @property
    def is_closed(self) -> bool:
        """Check if the archive is closed."""
        return self._closed


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. SQLITE BEST PRACTICES:
   - Use WAL mode for better concurrency
   - Use prepared statements
   - Use transactions for multi-row operations
   - Index frequently queried columns

2. DATA FORMAT:
   - Store as BLOB (FlatBuffer-serialized)
   - Metadata as JSON TEXT for flexibility
   - Timestamps as INTEGER (ms since epoch)

3. THREAD SAFETY:
   - SQLite handles thread safety in WAL mode
   - One connection per LocalColdArchive instance
   - Use connection pooling if needed

4. ERROR HANDLING:
   - Catch sqlite3.Error and wrap in ArchiveResult
   - Log all errors with session_id context
   - Never raise exceptions to caller

5. TESTING (tests/k1/sessionstate/test_local_cold.py):
   - Use pytest tmp_path for test databases
   - Test schema creation
   - Test archive/restore cycle
   - Test checkpoint/restore
   - Test prune
   - Test concurrent access (if applicable)
"""
