"""Shared helpers for M7 pseudo-K0 live-kernel probes."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
import uvicorn

from bridge._generated.k1.models.memory_write_v1 import MemoryWriteV1
from k1.concierge.config.kernel import KernelConfig
from scripts.pseudo_k0.connector_host import ConnectorHost
from scripts.pseudo_k0.server import create_app
from scripts.pseudo_k0.store import SQLiteK0Store
from tests.integration.k1.live.m6.helpers import recipe_a


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _UvicornThread(threading.Thread):
    def __init__(self, app: Any, host: str, port: int) -> None:
        super().__init__(daemon=True)
        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            lifespan="off",
        )
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        self.server.run()


class PseudoK0Handle:
    """Windows-safe in-process pseudo-K0 server handle for M7 probes."""

    def __init__(self, *, sse_heartbeat_s: float = 0.05) -> None:
        self.port = _free_port()
        self.endpoint = f"http://127.0.0.1:{self.port}"
        self.store = SQLiteK0Store(":memory:")
        self.connector_host = ConnectorHost()
        self.sse_heartbeat_s = sse_heartbeat_s
        self.app: Any | None = None
        self._thread: _UvicornThread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self.app = create_app(
            self.store,
            connector_host=self.connector_host,
            sse_heartbeat_s=self.sse_heartbeat_s,
        )
        thread = _UvicornThread(self.app, "127.0.0.1", self.port)
        thread.start()
        deadline = time.time() + 5.0
        while time.time() < deadline and not getattr(thread.server, "started", False):
            time.sleep(0.05)
        if not getattr(thread.server, "started", False):
            thread.server.should_exit = True
            raise RuntimeError("pseudo-K0 server failed to start")
        self._thread = thread

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        thread.server.should_exit = True
        thread.join(timeout=5.0)
        self._thread = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def close(self) -> None:
        self.stop()
        self.store.close()


@pytest.fixture
def pseudo_k0_server() -> Iterator[PseudoK0Handle]:
    handle = PseudoK0Handle()
    handle.start()
    try:
        yield handle
    finally:
        handle.close()


def recipe_c_pseudo_k0(
    tmp_path: Path,
    endpoint: str,
    **overrides: Any,
) -> KernelConfig:
    values: dict[str, Any] = {
        "bridge_enabled": True,
        "k0_endpoint": endpoint,
        "bridge_outbox_path": str(tmp_path / "bridge_outbox.db"),
        "selfmodel_space_id": "family:m7",
        "active_member_id": "actor:m7",
    }
    values.update(overrides)
    return recipe_a(tmp_path, **values)


def memory_write_payload(
    text: str,
    *,
    session_id: str = "m7",
    turn: int = 1,
) -> MemoryWriteV1:
    return MemoryWriteV1(
        schema_version="2.2",
        operation="UPSERT",
        text=text,
        topics=["m7"],
        sentiment_label="neutral",
        affect={"valence": 0.25, "arousal": 0.25, "dominance": 0.5},
        source_type="user_stated",
        novelty="NOVEL",
        elaboration_depth="MENTION",
        temporal_orientation="PAST",
        confidence=0.95,
        session_id=session_id,
        conversation_turn=turn,
        language="en",
    )


def wal_rows(store: SQLiteK0Store) -> list[dict[str, Any]]:
    with store._lock:  # noqa: SLF001 - live probe introspection
        rows = store._conn.execute(  # noqa: SLF001
            "SELECT id, topic, space_id, tenant_id, actor_id, band, trace_id, "
            "content, body, envelope FROM wal ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


async def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_s: float = 5.0,
    interval_s: float = 0.02,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval_s)
    raise AssertionError("condition was not met before timeout")


async def wait_for_sse_subscriber(handle: PseudoK0Handle, topic: str) -> None:
    def _has_subscriber() -> bool:
        app = handle.app
        broker = getattr(getattr(app, "state", None), "sse_broker", {}) if app else {}
        return bool(broker.get(topic))

    await wait_until(_has_subscriber, timeout_s=5.0)