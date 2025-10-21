"""Ward tests validating the metrics API exposure for cognitive readiness signals."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from fastapi.testclient import TestClient
from ward import fixture, test  # type: ignore[attr-defined]

from k0.automation.migrate import apply_migrations
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.kernel.readiness import ReadinessState


@fixture
def metrics_client() -> Iterator[TestClient]:
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "kernel.sqlite3"
        apply_migrations(db_path)

        settings = KernelSettings.load(overrides={"database": {"path": str(db_path)}})
        app = create_app(settings=settings)

        readiness = getattr(app.state, "readiness", None)
        if isinstance(readiness, ReadinessState):
            readiness.mark_migrations_complete()
            readiness.mark_wal_replay_complete()

        with TestClient(app) as client:
            # Trigger readiness gauges to emit into the metrics exporter.
            response = client.get("/readyz")
            assert response.status_code == 200
            yield client


@test("/metrics exposes readiness gauges for cognitive health tracking")
def _(metrics_client: TestClient = metrics_client) -> None:  # type: ignore[assignment]
    response = metrics_client.get("/metrics")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/plain")

    payload = response.text

    # Gauges emitted by /readyz signal overall readiness and component status.
    assert "kernel_ready_state" in payload
    assert "k0_kernel_kernel_ready_state 1.0" in payload
    assert (
        'k0_kernel_kernel_readiness_component_state{component="migrations_applied"} 1.0'
        in payload
    )
    assert (
        'k0_kernel_kernel_readiness_component_state{component="wal_replay_complete"} 1.0'
        in payload
    )


@test("/metrics honours Prometheus exposition format")
def _(metrics_client: TestClient = metrics_client) -> None:  # type: ignore[assignment]
    response = metrics_client.get("/metrics")
    assert response.status_code == 200

    # Prometheus exposition should include HELP/TYPE metadata for created gauges.
    body = response.text
    assert "# HELP k0_kernel_kernel_ready_state" in body
    assert "# TYPE k0_kernel_kernel_ready_state gauge" in body
    assert "# HELP k0_kernel_kernel_readiness_component_state" in body
    assert "# TYPE k0_kernel_kernel_readiness_component_state gauge" in body
    assert "Auto-generated gauge for kernel_ready_state" in body
    assert "Auto-generated gauge for kernel_readiness_component_state" in body
