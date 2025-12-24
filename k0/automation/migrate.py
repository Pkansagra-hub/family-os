"""Alembic-based migration runner for the K0 kernel storage schema.

This module provides a wrapper around Alembic for forward and rollback migration
support with dry-run validation and Prometheus telemetry.

Alembic Configuration:
  - Config file: k0/db/alembic.ini
  - Migrations: k0/db/alembic/versions/
  - Environment: k0/db/alembic/env.py (async PostgreSQL)

Telemetry (requires prometheus_client to be installed):
  - k0_migration_duration_seconds: Duration of migration application (histogram)
  - k0_migration_rollback_total: Total rollback operations (counter)
  - k0_migration_status: Last migration status (gauge: 1=success, 0=pending, -1=error)

Example:
  # Apply all pending migrations
  results = apply_migrations()

  # Apply migrations up to specific revision
  results = apply_migrations(target_revision="abc123")

  # Dry-run to see pending migrations
  results = apply_migrations(dry_run=True)

  # Rollback one revision
  results = rollback_migration(steps=1)

  # Rollback to specific revision
  results = rollback_migration(target_revision="abc123")
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

LOGGER = logging.getLogger(__name__)

# Path to alembic.ini (relative to this file's location in k0/automation/)
_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[1] / "db" / "alembic.ini"

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
    """Represents the outcome of a migration operation.

    Attributes
    ----------
    revision : str
        Alembic revision identifier (e.g., "abc123def456")
    action : str
        One of {"applied", "rolled_back", "skipped", "pending"}
    description : str
        Human-readable description of the migration
    duration_seconds : float | None
        Time taken to apply/rollback migration, or None if skipped
    """

    revision: str
    action: str  # one of {"applied", "rolled_back", "skipped", "pending"}
    description: str
    duration_seconds: float | None = None


def _get_alembic_config(
    alembic_ini_path: Optional[Path] = None,
    capture_output: bool = False,
) -> Config:
    """Create Alembic Config object.

    Parameters
    ----------
    alembic_ini_path:
        Path to alembic.ini file. Defaults to k0/db/alembic.ini.
    capture_output:
        If True, capture stdout for dry-run operations.

    Returns
    -------
    Config
        Configured Alembic Config object.
    """
    ini_path = alembic_ini_path or _ALEMBIC_INI_PATH

    if not ini_path.exists():
        raise MigrationError(f"Alembic config not found: {ini_path}")

    config = Config(str(ini_path))

    if capture_output:
        config.output_buffer = io.StringIO()

    return config


def _get_script_directory(config: Config) -> ScriptDirectory:
    """Get Alembic ScriptDirectory for inspecting migrations."""
    return ScriptDirectory.from_config(config)


def get_current_revision(
    alembic_ini_path: Optional[Path] = None,
) -> Optional[str]:
    """Get current database revision.

    Parameters
    ----------
    alembic_ini_path:
        Path to alembic.ini file.

    Returns
    -------
    str | None
        Current revision identifier, or None if no migrations applied.
    """
    config = _get_alembic_config(alembic_ini_path, capture_output=True)

    try:
        command.current(config)
        output = config.output_buffer.getvalue()  # type: ignore
        # Parse revision from output (format: "abc123 (head)")
        if output.strip():
            return output.strip().split()[0]
        return None
    except Exception as exc:
        raise MigrationError(f"Failed to get current revision: {exc}") from exc


def get_pending_revisions(
    alembic_ini_path: Optional[Path] = None,
) -> list[tuple[str, str]]:
    """Get list of pending migrations.

    Parameters
    ----------
    alembic_ini_path:
        Path to alembic.ini file.

    Returns
    -------
    list[tuple[str, str]]
        List of (revision, description) tuples for pending migrations.
    """
    config = _get_alembic_config(alembic_ini_path)
    script = _get_script_directory(config)

    current = get_current_revision(alembic_ini_path)
    head = script.get_current_head()

    if current == head:
        return []

    pending = []
    for revision in script.iterate_revisions(head, current):
        if revision.revision != current:
            pending.append((revision.revision, revision.doc or "No description"))

    return list(reversed(pending))


def apply_migrations(
    *,
    target_revision: str = "head",
    alembic_ini_path: Optional[Path] = None,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> list[MigrationResult]:
    """Apply Alembic migrations to the database.

    Parameters
    ----------
    target_revision:
        Target revision to migrate to. Default "head" applies all pending.
        Can be a specific revision identifier.
    alembic_ini_path:
        Path to alembic.ini file. Defaults to k0/db/alembic.ini.
    dry_run:
        When true, migrations are not executed but pending status is reported.
    logger:
        Optional logger instance for progress messages.

    Returns
    -------
    list[MigrationResult]
        List of migration results describing applied/pending migrations.

    Raises
    ------
    MigrationError
        If migration fails or configuration is invalid.
    """
    log = logger or LOGGER
    config = _get_alembic_config(alembic_ini_path)

    results: list[MigrationResult] = []

    # Get pending migrations
    pending = get_pending_revisions(alembic_ini_path)

    if not pending:
        log.info("No pending migrations; database is up to date")
        return results

    if dry_run:
        log.info("[dry-run] %d migration(s) pending", len(pending))
        for revision, description in pending:
            log.info("[dry-run] would apply: %s - %s", revision, description)
            results.append(
                MigrationResult(
                    revision=revision,
                    action="pending",
                    description=description,
                )
            )
        return results

    # Apply migrations
    log.info("Applying %d migration(s) to target: %s", len(pending), target_revision)
    start_time = datetime.now(timezone.utc)

    try:
        command.upgrade(config, target_revision)

        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()

        if _TELEMETRY_ENABLED:
            _migration_duration_histogram.observe(duration_seconds)
            _migration_status_gauge.set(1)

        # Report applied migrations
        for revision, description in pending:
            results.append(
                MigrationResult(
                    revision=revision,
                    action="applied",
                    description=description,
                    duration_seconds=duration_seconds / len(pending),  # Approximate per-migration
                )
            )

        log.info(
            "Successfully applied %d migration(s) in %.2fs",
            len(pending),
            duration_seconds,
        )

    except Exception as exc:
        if _TELEMETRY_ENABLED:
            _migration_status_gauge.set(-1)
        raise MigrationError(f"Migration failed: {exc}") from exc

    return results


def rollback_migration(
    *,
    steps: int = 1,
    target_revision: Optional[str] = None,
    alembic_ini_path: Optional[Path] = None,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> list[MigrationResult]:
    """Rollback applied migrations.

    Parameters
    ----------
    steps:
        Number of migrations to roll back (default: 1).
        Ignored if target_revision is specified.
    target_revision:
        Specific revision to roll back to. If provided, steps is ignored.
        Use "base" to roll back all migrations.
    alembic_ini_path:
        Path to alembic.ini file. Defaults to k0/db/alembic.ini.
    dry_run:
        When true, rollback is not executed but plan is reported.
    logger:
        Optional logger instance for progress messages.

    Returns
    -------
    list[MigrationResult]
        List of migration results describing rolled back migrations.

    Raises
    ------
    MigrationError
        If rollback fails or target revision is invalid.
    """
    log = logger or LOGGER
    config = _get_alembic_config(alembic_ini_path)
    script = _get_script_directory(config)

    results: list[MigrationResult] = []

    current = get_current_revision(alembic_ini_path)
    if current is None:
        log.info("No migrations applied; nothing to roll back")
        return results

    # Determine target
    if target_revision:
        target = target_revision
    else:
        target = f"-{steps}"

    # Get revisions that will be rolled back
    revisions_to_rollback: list[tuple[str, str]] = []
    if target_revision:
        for revision in script.iterate_revisions(current, target_revision):
            if revision.revision != target_revision:
                revisions_to_rollback.append((revision.revision, revision.doc or "No description"))
    else:
        # Get the last N revisions
        count = 0
        for revision in script.iterate_revisions(current, "base"):
            if count >= steps:
                break
            revisions_to_rollback.append((revision.revision, revision.doc or "No description"))
            count += 1

    if not revisions_to_rollback:
        log.info("No migrations to roll back")
        return results

    if dry_run:
        log.info("[dry-run] %d migration(s) would be rolled back", len(revisions_to_rollback))
        for revision, description in revisions_to_rollback:
            log.info("[dry-run] would rollback: %s - %s", revision, description)
            results.append(
                MigrationResult(
                    revision=revision,
                    action="pending",
                    description=description,
                )
            )
        return results

    # Execute rollback
    log.info("Rolling back %d migration(s)", len(revisions_to_rollback))
    start_time = datetime.now(timezone.utc)

    try:
        command.downgrade(config, target)

        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()

        if _TELEMETRY_ENABLED:
            _migration_rollback_counter.inc(len(revisions_to_rollback))
            _migration_duration_histogram.observe(duration_seconds)
            _migration_status_gauge.set(1)

        # Report rolled back migrations
        for revision, description in revisions_to_rollback:
            results.append(
                MigrationResult(
                    revision=revision,
                    action="rolled_back",
                    description=description,
                    duration_seconds=duration_seconds / len(revisions_to_rollback),
                )
            )

        log.info(
            "Successfully rolled back %d migration(s) in %.2fs",
            len(revisions_to_rollback),
            duration_seconds,
        )

    except Exception as exc:
        if _TELEMETRY_ENABLED:
            _migration_status_gauge.set(-1)
        raise MigrationError(f"Rollback failed: {exc}") from exc

    return results


def get_migration_history(
    alembic_ini_path: Optional[Path] = None,
) -> list[tuple[str, str, bool]]:
    """Get full migration history.

    Parameters
    ----------
    alembic_ini_path:
        Path to alembic.ini file.

    Returns
    -------
    list[tuple[str, str, bool]]
        List of (revision, description, is_applied) tuples.
    """
    config = _get_alembic_config(alembic_ini_path)
    script = _get_script_directory(config)

    current = get_current_revision(alembic_ini_path)

    history = []
    for revision in script.iterate_revisions(script.get_current_head(), "base"):
        is_applied = current is not None and revision.revision <= current
        history.append((revision.revision, revision.doc or "No description", is_applied))

    return list(reversed(history))


__all__ = [
    "MigrationError",
    "MigrationResult",
    "apply_migrations",
    "rollback_migration",
    "get_current_revision",
    "get_pending_revisions",
    "get_migration_history",
]
