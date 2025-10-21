from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from ward import fixture  # type: ignore[attr-defined]

from k0.uow.connection_pool import configure_pool, connection_scope, shutdown_pool

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


@fixture
def sqlite_runtime() -> Iterator[Path]:
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
    with connection_scope() as connection:
        connection.executescript(STORAGE_SQL_PATH.read_text())
        connection.commit()
    try:
        yield db_path
    finally:
        shutdown_pool()
        tmp_dir.cleanup()
