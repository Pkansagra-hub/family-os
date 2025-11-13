from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from ward import fixture, test  # type: ignore[attr-defined]

from k0.cli.k0ctl import main

REPO_ROOT = Path(__file__).resolve().parents[3]
STORAGE_SQL = (REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql").read_text()


@fixture
def schema_database() -> Iterator[Path]:
    tmp_dir = TemporaryDirectory()
    database_path = Path(tmp_dir.name) / "kernel.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(STORAGE_SQL)
        connection.commit()
    finally:
        connection.close()
    try:
        yield database_path
    finally:
        tmp_dir.cleanup()


def _fetch_status(database: Path, uri: str, version: str) -> str:
    connection = sqlite3.connect(database)
    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT status FROM schema_registry WHERE schema_uri=? AND version=?",
            (uri, version),
        ).fetchone()
    finally:
        connection.close()
    if row is None:  # pragma: no cover - defensive guard for failed assertions
        raise AssertionError(f"Schema {uri}@{version} missing from registry")
    return str(row["status"])


@test("k0ctl schema commands register, promote, and block versions")
def _(schema_db: Any = schema_database) -> None:
    uri = "schema://memory/topic"
    register_args = [
        "--set",
        f"database.path={schema_db}",
        "schema",
        "register",
        "--uri",
        uri,
        "--version",
        "1.0.0",
        "--sha256",
        "a" * 64,
    ]
    assert main(register_args) == 0
    assert _fetch_status(schema_db, uri, "1.0.0") == "REGISTERED"

    promote_args = [
        "--set",
        f"database.path={schema_db}",
        "schema",
        "promote",
        "--uri",
        uri,
        "--version",
        "1.0.0",
    ]
    assert main(promote_args) == 0
    assert _fetch_status(schema_db, uri, "1.0.0") == "ACTIVE"

    register_next_args = [
        "--set",
        f"database.path={schema_db}",
        "schema",
        "register",
        "--uri",
        uri,
        "--version",
        "2.0.0",
        "--sha256",
        "b" * 64,
        "--activate",
    ]
    assert main(register_next_args) == 0
    assert _fetch_status(schema_db, uri, "2.0.0") == "ACTIVE"
    assert _fetch_status(schema_db, uri, "1.0.0") == "DEPRECATED"

    block_args = [
        "--set",
        f"database.path={schema_db}",
        "schema",
        "block",
        "--uri",
        uri,
        "--version",
        "1.0.0",
        "--operator",
        "test_operator",
        "--reason",
        "sunset complete",
    ]
    assert main(block_args) == 0
    assert _fetch_status(schema_db, uri, "1.0.0") == "BLOCKED"
