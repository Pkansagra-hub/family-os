from __future__ import annotations

import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, List

from ward import fixture, test  # type: ignore[attr-defined]

from k0.uow.connection_pool import (
    PoolStats,
    configure_pool,
    connection_scope,
    get_pool,
    shutdown_pool,
)


@fixture
def configured_pool(tmp_path_factory=TemporaryDirectory) -> Callable[[int], Path]:
    created_dirs: List[TemporaryDirectory] = []

    def _configure(max_size: int = 4) -> Path:
        tmp_dir = TemporaryDirectory()
        created_dirs.append(tmp_dir)
        db_path = Path(tmp_dir.name) / "runtime.sqlite3"
        configure_pool(db_path, max_size=max_size, busy_timeout_ms=7_500)
        return db_path

    yield _configure

    shutdown_pool()
    for directory in created_dirs:
        directory.cleanup()


@test("connection pool applies WAL pragmas and busy timeout")
def _(configured_pool: Callable[[int], Path] = configured_pool) -> None:
    configured_pool(4)
    with connection_scope() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        temp_store = connection.execute("PRAGMA temp_store").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 7_500
    assert temp_store in {1, 2}  # MEMORY (1) or TEMP (2) per SQLite docs


@test("connection pool serves concurrent requests up to max capacity and recycles connections")
def _(configured_pool: Callable[[int], Path] = configured_pool) -> None:
    configured_pool(2)

    acquired_ids: List[int] = []
    ready_barrier = threading.Barrier(3)
    release_event = threading.Event()

    def _worker() -> None:
        with connection_scope() as connection:
            acquired_ids.append(id(connection))
            ready_barrier.wait()
            release_event.wait()

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()

    # wait until both workers have acquired their connections
    ready_barrier.wait()
    assert len(acquired_ids) == 2
    stats_during_use: PoolStats = get_pool().stats()
    assert stats_during_use.in_use == 2
    assert stats_during_use.created == 2

    release_event.set()
    for thread in threads:
        thread.join()

    # After release the connections become available again
    stats_after_release = get_pool().stats()
    assert stats_after_release.available == 2
    assert stats_after_release.in_use == 0

    with connection_scope() as connection:
        recycled_id = id(connection)

    assert recycled_id in acquired_ids
    shutdown_pool()