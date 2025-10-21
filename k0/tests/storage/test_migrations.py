from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from ward import fixture, test  # type: ignore[attr-defined]

from k0.automation.migrate import apply_migrations


@fixture
def temp_db_path() -> Iterator[Path]:
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "kernel.sqlite3"


@test("migration runner applies baseline schema and records catalog entries")
def _(temp_db_path: Path = temp_db_path) -> None:  # type: ignore[assignment]
    db_path = temp_db_path
    results = apply_migrations(db_path)

    baseline = [result for result in results if result.version == "0001_baseline"]
    assert baseline and baseline[0].action == "applied"
    applied_count = sum(1 for result in results if result.action == "applied")

    connection = sqlite3.connect(str(db_path))
    try:
        table_row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='st_wal'"
        ).fetchone()
        assert table_row is not None

        applied_rows = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()
        assert applied_rows is not None and applied_rows[0] == applied_count
    finally:
        connection.close()


@test("migration runner is idempotent on subsequent executions")
def _(temp_db_path: Path = temp_db_path) -> None:  # type: ignore[assignment]
    db_path = temp_db_path
    apply_migrations(db_path)
    second_pass = apply_migrations(db_path)

    for result in second_pass:
        assert result.action == "skipped"


@test("dry-run enumerates pending migrations without applying them")
def _(temp_db_path: Path = temp_db_path) -> None:  # type: ignore[assignment]
    db_path = temp_db_path
    pending = apply_migrations(db_path, dry_run=True)

    assert all(result.action == "pending" for result in pending)

    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        assert rows is not None and rows[0] == 0
    finally:
        connection.close()
