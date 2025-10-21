"""Integration tests for kernel health, readiness, and metrics probes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, cast

import ward
from fastapi import FastAPI
from fastapi.testclient import TestClient

from k0.kernel import ReadinessState, create_app


def _build_client() -> tuple[TestClient, ReadinessState]:
    app = create_app()
    readiness_state = getattr(app.state, "readiness")
    client = TestClient(app)
    return client, readiness_state


@ward.test("/healthz reports liveness with version metadata")
def _() -> None:
    client, _ = _build_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload


@ward.test("/readyz reports readiness after bootstrap and blocks when reset")
def _() -> None:
    client, readiness = _build_client()

    initial_response = client.get("/readyz")
    assert initial_response.status_code == 200
    payload = initial_response.json()
    assert payload["ready"] is True
    assert payload["components"] == {
        "migrations_applied": True,
        "wal_replay_complete": True,
    }

    readiness.reset()

    blocked_response = client.get("/readyz")
    assert blocked_response.status_code == 503
    blocked_payload = blocked_response.json()
    assert blocked_payload["ready"] is False
    assert blocked_payload["components"] == {
        "migrations_applied": False,
        "wal_replay_complete": False,
    }

    readiness.mark_migrations_complete()
    readiness.mark_wal_replay_complete()

    ready_response = client.get("/readyz")
    assert ready_response.status_code == 200
    ready_payload = ready_response.json()
    assert ready_payload["ready"] is True
    assert ready_payload["components"] == {
        "migrations_applied": True,
        "wal_replay_complete": True,
    }


@ward.test("/metrics exposes readiness gauges")
def _() -> None:
    client, readiness = _build_client()

    # Prime gauges with an initial readiness evaluation.
    client.get("/readyz")

    readiness.reset()
    readiness.mark_migrations_complete()
    readiness.mark_wal_replay_complete()
    client.get("/readyz")

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "kernel_ready_state" in body
    assert 'component="migrations_applied"' in body
    assert 'component="wal_replay_complete"' in body


@ward.test("startup bootstrap applies database migrations")
def _() -> None:
    client, _ = _build_client()
    app = cast(FastAPI, client.app)
    state = cast(Any, app.state)
    db_path = Path(state.settings.database.path)
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='st_devices'"
        ).fetchone()
        assert row is not None
