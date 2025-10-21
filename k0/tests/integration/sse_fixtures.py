from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Iterator

from fastapi.testclient import TestClient
from ward import fixture  # type: ignore[attr-defined]

from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.uow.connection_pool import connection_scope, shutdown_pool

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


class SSETestEnv(SimpleNamespace):
    client: TestClient
    app: Any


@fixture
def sse_env() -> Iterator[SSETestEnv]:
    tmp_dir = TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"

    settings = KernelSettings.load(
        overrides={
            "database": {"path": str(db_path)},
            "telemetry": {"otlp_endpoint": None},
        }
    )
    app = create_app(settings=settings)

    storage_sql = STORAGE_SQL_PATH.read_text(encoding="utf-8")
    with connection_scope() as conn:
        conn.executescript(storage_sql)
        conn.commit()

    observability = getattr(app.state, "observability_emitter", None)
    if observability is not None:
        observability.clear()

    with TestClient(app) as client:
        yield SSETestEnv(client=client, app=app)

    shutdown_pool()
    tmp_dir.cleanup()


@contextmanager
def sse_environment(kernel_harness: Any) -> Iterator[SSETestEnv]:
    """Context manager that provides SSETestEnv from KernelHarness.

    This allows tests migrated to use kernel_harness fixture to access
    the SSE test environment in a compatible way.
    """
    # Access the app from kernel_harness.client which wraps TestClient
    app = kernel_harness.client.app
    client = kernel_harness.client
    yield SSETestEnv(client=client, app=app)
