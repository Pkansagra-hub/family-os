"""SQLite migration runner for the K0 kernel storage schema.

This module provides forward and rollback migration support with dry-run validation
and Prometheus telemetry. Migrations are applied in alphabetical order; rollbacks
are applied in reverse order.

Telemetry (requires prometheus_client to be installed):
  - k0_migration_duration_seconds: Duration of migration application (histogram)
  - k0_migration_rollback_total: Total rollback operations (counter)
  - k0_migration_status: Last migration status (gauge: 1=success, 0=pending, -1=error)

Example:
  # Apply forward migrations
  results = apply_migrations(Path("mydb.db"))

  # Dry-run rollback to version 0001
  results = rollback_migration(
      Path("mydb.db"),
      target_version="0001",
      dry_run=True,
  )

  # Execute rollback to version 0001
  results = rollback_migration(
      Path("mydb.db"),
      target_version="0001",
      dry_run=False,
  )
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "contracts" / "sql" / "migrations"

# Prometheus telemetry (optional, graceful degradation if not installed)
try:
    from prometheus_client import Counter, Gauge, Histogram

    _migration_duration_histogram = Histogram(
        "k0_migration_duration_seconds",
        "Duration of migration application in seconds",
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0),
    )
    _migration_rollback_counter = Counter(
        "k0_migration_rollback_total",
        "Total number of rollback operations",
    )
    _migration_status_gauge = Gauge(
        "k0_migration_status",
        "Last migration status: 1=success, 0=pending, -1=error",
    )
    _TELEMETRY_ENABLED = True
except ImportError:
    _TELEMETRY_ENABLED = False


class MigrationError(RuntimeError):
    """Raised when a migration fails or the migration graph is inconsistent."""


@dataclass(slots=True)
class MigrationResult:
    """Represents the outcome of evaluating a migration file.

    Attributes
    ----------
    version : str
        Version identifier (e.g., "0001_baseline")
    action : str
        One of {"applied", "rolled_back", "skipped", "pending"}
    checksum : str
        SHA256 hash of the migration script
    path : Path
        Filesystem path to the migration file
    duration_seconds : float | None
        Time taken to apply/rollback migration, or None if skipped
    rollback_script : str | None
        Auto-generated rollback script, or None if forward migration
    """

    version: str
    action: str  # one of {"applied", "rolled_back", "skipped", "pending"}
    checksum: str
    path: Path
    duration_seconds: float | None = None
    rollback_script: str | None = None


def apply_migrations(
    database_path: Path | str,
    *,
    migrations_path: Path | str | None = None,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> list[MigrationResult]:
    """Apply SQLite migrations to the provided database.

    Migrations are applied in alphabetical order. Each migration is wrapped in a
    transaction and recorded in the schema_migrations catalog.

    Parameters
    ----------
    database_path:
        Filesystem path to the SQLite database file.
    migrations_path:
        Directory containing ``*.sql`` migration files. Defaults to the
        repository's ``k0/contracts/sql/migrations`` directory.
    dry_run:
        When true, migrations are not executed but their pending status is
        reported. The schema_migrations catalog is left untouched.
    logger:
        Optional logger instance to emit progress messages.

    Returns
    -------
    list[MigrationResult]
        Ordered list describing whether each migration was applied, skipped, or
        remains pending when running in dry-run mode. Includes duration_seconds
        for applied migrations (for telemetry).

    Raises
    ------
    MigrationError
        If migration directory doesn't exist, no migrations found, or a migration
        fails to apply (due to schema errors or checksum mismatch).
    """

    log = logger or LOGGER
    db_path = Path(database_path)
    migrations_dir = Path(migrations_path) if migrations_path else _DEFAULT_MIGRATIONS_DIR

    if not migrations_dir.exists():
        raise MigrationError(f"Migration directory does not exist: {migrations_dir}")
    if not migrations_dir.is_dir():
        raise MigrationError(f"Migration path is not a directory: {migrations_dir}")

    migration_files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    if not migration_files:
        raise MigrationError(f"No migration files found in {migrations_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[MigrationResult] = []

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA busy_timeout=5000;")
        _ensure_catalog(connection)
        applied = _load_applied(connection)

        for migration_path in migration_files:
            version = migration_path.stem
            script = migration_path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(script.encode("utf-8")).hexdigest()

            if version in applied:
                recorded_checksum = applied[version]
                if recorded_checksum != checksum:
                    raise MigrationError(
                        (
                            "Checksum mismatch for migration "
                            f"'{version}'. Expected {recorded_checksum}, found {checksum}"
                        )
                    )
                results.append(
                    MigrationResult(
                        version=version,
                        action="skipped",
                        checksum=checksum,
                        path=migration_path,
                    )
                )
                continue

            if dry_run:
                log.info("[dry-run] would apply migration %s", version)
                results.append(
                    MigrationResult(
                        version=version,
                        action="pending",
                        checksum=checksum,
                        path=migration_path,
                    )
                )
                continue

            log.info("Applying migration %s", version)
            start_time = datetime.now(timezone.utc)
            try:
                connection.execute("BEGIN")
                connection.executescript(script)
                connection.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (
                        version,
                        checksum,
                        _utc_timestamp(),
                    ),
                )
                connection.commit()
            except Exception as exc:  # pragma: no cover - defensive rollback
                connection.rollback()
                if _TELEMETRY_ENABLED:
                    _migration_status_gauge.set(-1)
                raise MigrationError(f"Failed to apply migration {version}") from exc

            duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
            if _TELEMETRY_ENABLED:
                _migration_duration_histogram.observe(duration_seconds)
                _migration_status_gauge.set(1)

            results.append(
                MigrationResult(
                    version=version,
                    action="applied",
                    checksum=checksum,
                    path=migration_path,
                    duration_seconds=duration_seconds,
                )
            )

        connection.execute("PRAGMA wal_checkpoint(FULL);")
    finally:
        connection.close()

    return results


def rollback_migration(
    database_path: Path | str,
    *,
    target_version: str,
    migrations_path: Path | str | None = None,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> list[MigrationResult]:
    """Rollback applied migrations to the specified target version.

    Migrations are rolled back in reverse alphabetical order (newest first).
    This function is intended for emergency recovery; manual rollback scripts
    are recommended for complex migrations.

    For each migration to be rolled back, a DOWN script is auto-generated by
    reversing the DDL statements from the UP script (best-effort).

    Parameters
    ----------
    database_path:
        Filesystem path to the SQLite database file.
    target_version:
        Version to roll back to (inclusive; this version will remain applied).
        If target_version is "0001", migrations 0001 and earlier are kept;
        all newer migrations are rolled back.
    migrations_path:
        Directory containing ``*.sql`` migration files. Defaults to the
        repository's ``k0/contracts/sql/migrations`` directory.
    dry_run:
        When true, rollback plan is generated and validated but not executed.
        The schema_migrations catalog is left untouched.
    logger:
        Optional logger instance to emit progress messages.

    Returns
    -------
    list[MigrationResult]
        Ordered list describing rollback status for each migration.
        Each result includes the auto-generated rollback_script if available.

    Raises
    ------
    MigrationError
        If target_version does not exist in applied migrations, or if
        rollback fails due to schema errors or cascade constraints.
    """

    log = logger or LOGGER
    db_path = Path(database_path)
    migrations_dir = Path(migrations_path) if migrations_path else _DEFAULT_MIGRATIONS_DIR

    if not migrations_dir.exists():
        raise MigrationError(f"Migration directory does not exist: {migrations_dir}")
    if not migrations_dir.is_dir():
        raise MigrationError(f"Migration path is not a directory: {migrations_dir}")

    migration_files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    if not migration_files:
        raise MigrationError(f"No migration files found in {migrations_dir}")

    if not db_path.exists():
        raise MigrationError(f"Database does not exist: {db_path}")

    results: list[MigrationResult] = []
    connection = sqlite3.connect(str(db_path))

    try:
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA busy_timeout=5000;")
        _ensure_catalog(connection)
        applied = _load_applied(connection)

        # Validate target_version exists
        if target_version not in applied:
            raise MigrationError(
                f"Target version '{target_version}' not found in applied migrations"
            )

        # Determine migrations to roll back (in reverse order)
        migration_files_sorted = sorted(migration_files, key=lambda p: p.stem)
        migrations_to_rollback = [
            p for p in migration_files_sorted if p.stem > target_version and p.stem in applied
        ]
        migrations_to_rollback.reverse()  # Newest first

        if not migrations_to_rollback:
            log.info("No migrations to roll back; already at target version %s", target_version)
            return results

        log.info(
            "Rolling back %d migration(s) from %s to %s",
            len(migrations_to_rollback),
            migration_files_sorted[-1].stem,
            target_version,
        )

        for migration_path in migrations_to_rollback:
            version = migration_path.stem
            up_script = migration_path.read_text(encoding="utf-8")
            down_script = generate_rollback_script(up_script)
            checksum = hashlib.sha256(up_script.encode("utf-8")).hexdigest()

            if dry_run:
                log.info(
                    "[dry-run] would rollback migration %s\n%s",
                    version,
                    down_script,
                )
                results.append(
                    MigrationResult(
                        version=version,
                        action="pending",
                        checksum=checksum,
                        path=migration_path,
                        rollback_script=down_script,
                    )
                )
                continue

            log.info("Rolling back migration %s", version)
            start_time = datetime.now(timezone.utc)
            try:
                connection.execute("BEGIN")
                connection.executescript(down_script)
                connection.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (version,),
                )
                connection.commit()
            except Exception as exc:  # pragma: no cover - defensive rollback
                connection.rollback()
                if _TELEMETRY_ENABLED:
                    _migration_status_gauge.set(-1)
                raise MigrationError(f"Failed to rollback migration {version}") from exc

            duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
            if _TELEMETRY_ENABLED:
                _migration_rollback_counter.inc()
                _migration_duration_histogram.observe(duration_seconds)
                _migration_status_gauge.set(1)

            results.append(
                MigrationResult(
                    version=version,
                    action="rolled_back",
                    checksum=checksum,
                    path=migration_path,
                    duration_seconds=duration_seconds,
                    rollback_script=down_script,
                )
            )

        connection.execute("PRAGMA wal_checkpoint(FULL);")
    finally:
        connection.close()

    return results


def generate_rollback_script(up_script: str) -> str:
    """Auto-generate a DOWN migration script from an UP script (best-effort).

    This function attempts to reverse DDL statements by:
    - Converting CREATE TABLE to DROP TABLE
    - Converting CREATE INDEX to DROP INDEX
    - Converting ALTER TABLE ADD to ALTER TABLE DROP (limited support)
    - Removing DML statements (INSERT, UPDATE, DELETE)
    - Removing comments and pragmas

    For complex migrations, this generates a best-effort script that may
    require manual refinement. Inspect generated scripts carefully.

    Parameters
    ----------
    up_script : str
        The complete UP migration script (as read from disk).

    Returns
    -------
    str
        Auto-generated DOWN migration script with reversed DDL statements.
        Statements are reversed in reverse order (newest first).

    Notes
    -----
    - This is best-effort; complex migrations may require manual DOWN scripts
    - The function preserves transaction structure (BEGIN/COMMIT)
    - Pragmas and comments are removed
    - Foreign keys are disabled during rollback to avoid cascade issues
    """

    lines = up_script.split("\n")
    down_statements: list[str] = []
    up_statements: list[str] = []

    current_statement = ""
    for line in lines:
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("--"):
            continue

        # Skip pragma statements
        if stripped.upper().startswith("PRAGMA"):
            continue

        current_statement += " " + line

        # Statement ends with semicolon
        if stripped.endswith(";"):
            statement = current_statement.strip()
            up_statements.append(statement)
            current_statement = ""

    # Reverse statements and generate DOWN equivalents
    for statement in reversed(up_statements):
        stmt_upper = statement.upper()

        if stmt_upper.startswith("CREATE TABLE"):
            # CREATE TABLE foo (...) -> DROP TABLE IF EXISTS foo
            table_name = _extract_name_after_keyword(statement, "TABLE")
            if table_name:
                down_statements.append(f"DROP TABLE IF EXISTS {table_name};")

        elif stmt_upper.startswith("CREATE INDEX") or stmt_upper.startswith("CREATE UNIQUE INDEX"):
            # CREATE [UNIQUE] INDEX idx_foo ON table(...) -> DROP INDEX IF EXISTS idx_foo
            index_name = _extract_name_after_keyword(statement, "INDEX")
            if index_name:
                down_statements.append(f"DROP INDEX IF EXISTS {index_name};")

        elif stmt_upper.startswith("CREATE TRIGGER"):
            # CREATE TRIGGER trg_foo -> DROP TRIGGER IF EXISTS trg_foo
            trigger_name = _extract_name_after_keyword(statement, "TRIGGER")
            if trigger_name:
                down_statements.append(f"DROP TRIGGER IF EXISTS {trigger_name};")

        elif stmt_upper.startswith("ALTER TABLE"):
            # ALTER TABLE foo ADD COLUMN bar ... -> ALTER TABLE foo DROP COLUMN bar
            # This is best-effort; complex ALTER statements may not parse correctly
            if "ADD COLUMN" in stmt_upper:
                col_name = _extract_column_name_from_alter(statement)
                table_name = _extract_name_after_keyword(statement, "TABLE")
                if table_name and col_name:
                    down_statements.append(f"ALTER TABLE {table_name} DROP COLUMN {col_name};")

    # Build final DOWN script
    down_script_lines = [
        "-- Auto-generated DOWN migration (best-effort)",
        "-- Review and adjust as needed for complex operations",
        "",
        "BEGIN;",
        "",
        "PRAGMA foreign_keys=OFF;",
        "",
    ]

    down_script_lines.extend(down_statements)

    down_script_lines.extend(
        [
            "",
            "PRAGMA foreign_keys=ON;",
            "",
            "COMMIT;",
        ]
    )

    return "\n".join(down_script_lines)


def _extract_name_after_keyword(statement: str, keyword: str) -> str | None:
    """Extract identifier name after keyword (e.g., 'TABLE foo' -> 'foo')."""
    pattern = keyword + r"\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)"
    match_obj = re.search(pattern, statement, re.IGNORECASE)
    return match_obj.group(1) if match_obj else None


def _extract_column_name_from_alter(statement: str) -> str | None:
    """Extract column name from ALTER TABLE ADD COLUMN statement."""
    pattern = r"ADD\s+COLUMN\s+(\w+)"
    match_obj = re.search(pattern, statement, re.IGNORECASE)
    return match_obj.group(1) if match_obj else None


def _ensure_catalog(connection: sqlite3.Connection) -> None:
    """Create schema_migrations table if it doesn't exist."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _load_applied(connection: sqlite3.Connection) -> dict[str, str]:
    """Load all applied migrations from schema_migrations catalog."""
    cursor = connection.execute("SELECT version, checksum FROM schema_migrations")
    return {row[0]: row[1] for row in cursor.fetchall()}


def _utc_timestamp() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "MigrationError",
    "MigrationResult",
    "apply_migrations",
    "rollback_migration",
    "generate_rollback_script",
]
