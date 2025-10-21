from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from ward import fixture, test  # type: ignore[attr-defined]

from k0.cli.k0ctl import main

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL = (REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql").read_text()


@fixture
def dlq_database() -> Iterator[Path]:
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


def _insert_dlq_entry(
    database: Path,
    *,
    wal_pos: int,
    tenant_id: str,
    space_id: str,
    driver: str,
    op_kind: str,
    fingerprint: str,
    payload: bytes,
    reason: str,
    retries: int,
    requeue_seq: int,
    first_failure_ts: str,
    last_failure_ts: str,
    state: str = "PENDING",
) -> int:
    connection = sqlite3.connect(database)
    try:
        cursor = connection.execute(
            (
                "INSERT INTO st_dlq (wal_pos, tenant_id, space_id, driver, op_kind, fingerprint, payload, reason, "
                "retries, requeue_seq, first_failure_ts, last_failure_ts, state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                wal_pos,
                tenant_id,
                space_id,
                driver,
                op_kind,
                fingerprint,
                sqlite3.Binary(payload),
                reason,
                retries,
                requeue_seq,
                first_failure_ts,
                last_failure_ts,
                state,
            ),
        )
        connection.commit()
        row_id = cursor.lastrowid
    finally:
        connection.close()
    if row_id is None:  # pragma: no cover - SQLite guarantees row id
        raise AssertionError("Failed to insert DLQ entry")
    return int(row_id)


@test("k0ctl dlq list returns success when entries exist")
def _(dlq_db: Any = dlq_database) -> None:
    entry_id = _insert_dlq_entry(
        dlq_db,
        wal_pos=10,
        tenant_id="tenant-1",
        space_id="space-1",
        driver="driver-A",
        op_kind="UPSERT",
        fingerprint="fingerprint-1",
        payload=b"payload",
        reason="driver-A:RuntimeError:boom",
        retries=3,
        requeue_seq=1,
        first_failure_ts="2025-09-28T12:00:00Z",
        last_failure_ts="2025-09-28T12:01:00Z",
    )
    assert entry_id > 0

    args = [
        "--set",
        f"database.path={dlq_db}",
        "dlq",
        "list",
        "--limit",
        "10",
    ]
    assert main(args) == 0


@test("k0ctl dlq requeue reinserts outbox entry and marks state")
def _(dlq_db: Any = dlq_database) -> None:
    entry_id = _insert_dlq_entry(
        dlq_db,
        wal_pos=20,
        tenant_id="tenant-1",
        space_id="space-1",
        driver="driver-A",
        op_kind="UPSERT",
        fingerprint="fingerprint-2",
        payload=b"payload",
        reason="driver-A:RuntimeError:boom",
        retries=5,
        requeue_seq=2,
        first_failure_ts="2025-09-28T12:00:00Z",
        last_failure_ts="2025-09-28T12:02:00Z",
    )

    args = [
        "--set",
        f"database.path={dlq_db}",
        "dlq",
        "requeue",
        "--id",
        str(entry_id),
    ]
    assert main(args) == 0

    connection = sqlite3.connect(dlq_db)
    connection.row_factory = sqlite3.Row
    try:
        outbox_row = connection.execute(
            "SELECT driver, fingerprint, requeue_seq, retries, last_error FROM st_outbox"
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row["driver"] == "driver-A"
        assert outbox_row["fingerprint"] == "fingerprint-2"
        assert outbox_row["requeue_seq"] == 3
        assert outbox_row["retries"] == 0
        assert outbox_row["last_error"].startswith("driver-A:RuntimeError")

        dlq_row = connection.execute(
            "SELECT state, requeue_seq FROM st_dlq WHERE id=?",
            (entry_id,),
        ).fetchone()
        assert dlq_row is not None
        assert dlq_row["state"] == "REQUEUED"
        assert dlq_row["requeue_seq"] == 3
    finally:
        connection.close()


@test("k0ctl dlq purge marks entries as quarantined")
def _(dlq_db: Any = dlq_database) -> None:
    entry_id = _insert_dlq_entry(
        dlq_db,
        wal_pos=30,
        tenant_id="tenant-1",
        space_id="space-1",
        driver="driver-A",
        op_kind="UPSERT",
        fingerprint="fingerprint-3",
        payload=b"payload",
        reason="driver-A:RuntimeError:boom",
        retries=2,
        requeue_seq=1,
        first_failure_ts="2025-09-28T12:00:00Z",
        last_failure_ts="2025-09-28T12:03:00Z",
    )

    args = [
        "--set",
        f"database.path={dlq_db}",
        "dlq",
        "purge",
        "--id",
        str(entry_id),
    ]
    assert main(args) == 0

    connection = sqlite3.connect(dlq_db)
    connection.row_factory = sqlite3.Row
    try:
        dlq_row = connection.execute(
            "SELECT state FROM st_dlq WHERE id=?",
            (entry_id,),
        ).fetchone()
        assert dlq_row is not None
        assert dlq_row["state"] == "QUARANTINED"
    finally:
        connection.close()
