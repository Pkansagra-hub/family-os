"""SQLite migration runner for the K0 kernel storage schema."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_DEFAULT_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[1] / "contracts" / "sql" / "migrations"
)


class MigrationError(RuntimeError):
    """Raised when a migration fails or the migration graph is inconsistent."""


@dataclass(slots=True)
class MigrationResult:
    """Represents the outcome of evaluating a migration file."""

    version: str
    action: str  # one of {"applied", "skipped", "pending"}
    checksum: str
    path: Path


def apply_migrations(
    database_path: Path | str,
    *,
    migrations_path: Path | str | None = None,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> list[MigrationResult]:
    """Apply SQLite migrations to the provided database.

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
        remains pending when running in dry-run mode.
    """

    log = logger or LOGGER
    db_path = Path(database_path)
    migrations_dir = (
        Path(migrations_path) if migrations_path else _DEFAULT_MIGRATIONS_DIR
    )

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
                raise MigrationError(f"Failed to apply migration {version}") from exc

            results.append(
                MigrationResult(
                    version=version,
                    action="applied",
                    checksum=checksum,
                    path=migration_path,
                )
            )

        connection.execute("PRAGMA wal_checkpoint(FULL);")
    finally:
        connection.close()

    return results


def _ensure_catalog(connection: sqlite3.Connection) -> None:
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
    cursor = connection.execute("SELECT version, checksum FROM schema_migrations")
    return {row[0]: row[1] for row in cursor.fetchall()}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "MigrationError",
    "MigrationResult",
    "apply_migrations",
]
