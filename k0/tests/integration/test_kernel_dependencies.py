from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Union

from fastapi import Depends
from fastapi.testclient import TestClient
from ward import test

from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.kernel.dependencies import build_request_dependencies, database_session


opened_connection_ids: List[int] = []
closed_connection_ids: List[int] = []
connection_close_counts: Dict[int, int] = {}


class TrackingConnection(sqlite3.Connection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        opened_connection_ids.append(id(self))

    def close(self) -> None:  # type: ignore[override]
        conn_id = id(self)
        if connection_close_counts.get(conn_id, 0) == 0:
            closed_connection_ids.append(conn_id)
        connection_close_counts[conn_id] = connection_close_counts.get(conn_id, 0) + 1
        super().close()


def _instrumented_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(db_path),
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
        factory=TrackingConnection,
    )
    return connection


@test("database sessions are unique per request and closed after use")
def _( ) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "runtime.sqlite3"
        settings = KernelSettings.load(overrides={"database": {"path": str(db_path)}})
        app = create_app(settings=settings)

        @app.get("/probe")
        def probe(conn: sqlite3.Connection = Depends(database_session)) -> dict[str, int]:
            conn.execute("CREATE TABLE IF NOT EXISTS probe(value TEXT)")
            conn.execute("INSERT INTO probe(value) VALUES ('ok')")
            conn.commit()
            (count,) = conn.execute("SELECT COUNT(*) FROM probe").fetchone()
            return {"count": int(count)}

        _ = probe  # silence static analysis about unused local function

        provider = build_request_dependencies(
            settings=settings,
            connection_factory=lambda: _instrumented_connection(settings.database.path),
        )
        app.dependency_overrides.update(provider.as_fastapi_overrides())

        client = TestClient(app)
        opened_connection_ids.clear()
        closed_connection_ids.clear()
        connection_close_counts.clear()

        response_a = client.get("/probe")
        assert response_a.status_code == 200
        assert response_a.json()["count"] == 1
        assert len(opened_connection_ids) == 1
        assert len(closed_connection_ids) == 1
        first_id = opened_connection_ids[0]
        assert connection_close_counts.get(first_id, 0) == 1

        response_b = client.get("/probe")
        assert response_b.status_code == 200
        assert response_b.json()["count"] == 2
        assert len(opened_connection_ids) == 2
        assert len(closed_connection_ids) == 2
        assert opened_connection_ids[0] != opened_connection_ids[1]
        assert set(closed_connection_ids) == set(opened_connection_ids)
        assert all(connection_close_counts.get(conn_id, 0) == 1 for conn_id in closed_connection_ids)
