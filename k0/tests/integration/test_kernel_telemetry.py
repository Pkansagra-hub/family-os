from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator, cast

from fastapi.testclient import TestClient
from ward import test  # type: ignore[attr-defined]

from k0.bus import BusDispatcher
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.uow.connection_pool import connection_scope, shutdown_pool

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


@contextmanager
def _telemetry_client() -> Iterator[TestClient]:
    tmp_dir = TemporaryDirectory()
    try:
        db_path = Path(tmp_dir.name) / "telemetry.sqlite3"

        settings = KernelSettings.load(
            overrides={
                "database": {"path": str(db_path)},
                "telemetry": {"otlp_endpoint": None},
            }
        )
        app = create_app(settings=settings)

        storage_sql = STORAGE_SQL_PATH.read_text(encoding="utf-8")
        with connection_scope() as connection:
            connection.executescript(storage_sql)
            connection.commit()
        with connection_scope() as connection:
            table_names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        if "st_wal" not in table_names:
            msg = "storage schema bootstrap failed: st_wal missing"
            raise RuntimeError(msg)

        with TestClient(app) as client:
            yield client
    finally:
        shutdown_pool()
        tmp_dir.cleanup()


@test("middleware preserves incoming cognitive trace identifier")
def _() -> None:
    with _telemetry_client() as client:
        payload: dict[str, object] = {
            "selectors": [{"topic": "memory.topic"}],
            "space_id": "space-test",
        }
        response = client.post(
            "/k0/query.recall",
            json=payload,
            headers={"X-Cognitive-Trace-Id": "trace-fixed"},
        )
        assert response.headers["X-Cognitive-Trace-Id"] == "trace-fixed"
        assert response.status_code == 200


@test("middleware generates new cognitive trace identifier when header missing")
def _() -> None:
    with _telemetry_client() as client:
        payload: dict[str, object] = {
            "selectors": [{"topic": "memory.topic"}],
            "space_id": "space-test",
        }
        response = client.post("/k0/query.recall", json=payload)
        trace_id = response.headers.get("X-Cognitive-Trace-Id")
        assert trace_id is not None
        assert len(trace_id) == 32
        int(trace_id, 16)
        assert response.status_code == 200


@test("telemetry objects are attached to the FastAPI application state")
def _() -> None:
    with _telemetry_client() as client:
        app_state = cast(Any, client.app).state

        assert hasattr(app_state, "tracer_factory")
        assert hasattr(app_state, "metrics_exporter")


@test("bus dispatcher honours middleware toggles from configuration")
def _() -> None:
    settings = KernelSettings.load(
        overrides={
            "telemetry": {"otlp_endpoint": None},
            "bus": {
                "middleware": {
                    "timestamps_enabled": False,
                    "tracing_enabled": False,
                    "metrics_enabled": False,
                }
            },
        }
    )
    app = create_app(settings=settings)
    try:
        dispatcher = getattr(app.state, "bus_dispatcher", None)
        assert isinstance(dispatcher, BusDispatcher)
        assert dispatcher.middlewares == ()
    finally:
        shutdown_pool()
