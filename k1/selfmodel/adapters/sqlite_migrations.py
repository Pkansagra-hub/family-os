"""``sqlite_migrations`` — ``PRAGMA user_version`` migration runner.

Issue M3.E4.I2.

Conventions:

* Migration files live in ``k1/selfmodel/migrations/`` and are named
  ``NNNN_description.sql`` where ``NNNN`` is the target ``user_version``
  *after* the migration applies (i.e. ``0001_initial.sql`` lifts a
  fresh database from version 0 to version 1).
* Migrations are applied in numeric order, each in its own transaction.
* Re-running on a partially-migrated database picks up where it left
  off (driven entirely by ``PRAGMA user_version``).
* Downgrade is refused — the runner raises if a SQL file targets a
  version <= the current one when called directly via
  :func:`apply_migrations`.

This is a deliberately tiny runner; we don't need Alembic-style
machinery for the selfmodel store.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

__all__ = [
    "Migration",
    "apply_migrations",
    "discover_migrations",
    "current_user_version",
]

logger = logging.getLogger(__name__)


_NAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True)
class Migration:
    """One SQL file targeting a specific ``user_version``."""

    target_version: int
    name: str
    sql: str


# ---------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------
def discover_migrations(directory: Path | None = None) -> tuple[Migration, ...]:
    """List all migrations in numeric order."""
    found: list[Migration] = []
    if directory is None:
        files = resources.files("k1.selfmodel.migrations").iterdir()
    else:
        files = sorted(Path(directory).iterdir())
    for entry in files:
        name = entry.name
        match = _NAME_RE.match(name)
        if not match:
            continue
        target = int(match.group(1))
        sql = entry.read_text(encoding="utf-8")
        found.append(Migration(target_version=target, name=name, sql=sql))
    found.sort(key=lambda m: m.target_version)
    # Sanity check: contiguous, starting at 1.
    for expected, m in enumerate(found, start=1):
        if m.target_version != expected:
            raise RuntimeError(
                f"migration {m.name!r} targets version {m.target_version} "
                f"but expected {expected} (migrations must be contiguous starting at 1)"
            )
    return tuple(found)


# ---------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------
def current_user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def apply_migrations(
    conn: sqlite3.Connection,
    *,
    migrations: Iterable[Migration] | None = None,
) -> int:
    """Apply pending migrations to ``conn``.

    Returns the new ``user_version``. Raises ``RuntimeError`` if a
    discovered migration targets a version <= the current one (i.e. an
    attempted downgrade).
    """
    pending = tuple(migrations) if migrations is not None else discover_migrations()
    if not pending:
        return current_user_version(conn)
    current = current_user_version(conn)
    for migration in pending:
        if migration.target_version <= current:
            continue
        if migration.target_version != current + 1:
            raise RuntimeError(
                f"migration gap: at user_version={current}, next migration is "
                f"{migration.name!r} targeting {migration.target_version}"
            )
        logger.info(
            "selfmodel.migrations: applying %s (-> user_version=%d)",
            migration.name,
            migration.target_version,
        )
        try:
            conn.execute("BEGIN")
            conn.executescript(migration.sql)
            conn.execute(f"PRAGMA user_version = {migration.target_version}")
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        current = migration.target_version
    return current
