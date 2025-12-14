from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

from ward import fixture, test  # type: ignore[attr-defined]

from k0.outbox import DriverWorkerPool, compute_fingerprint
from k0.storage.outbox import OutboxEntry
from k0.tests.integration.sse_fixtures import sse_env  # type: ignore[misc]


class _RecordingHandler(BaseHTTPRequestHandler):
    records: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: D401 - HTTP handler signature is fixed
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.records.append(
            {
                "path": self.path,
                "session": self.headers.get("X-K0-Driver-Session"),
                "body": body,
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(
        self, format: str, *args: Any
    ) -> None:  # pragma: no cover - silence logs
        return


@fixture
def handshake_server() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    _RecordingHandler.records = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.timeout = 0.5
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        address = server.server_address
        host = address[0]
        port = address[1]
        yield (f"http://{host}:{port}/apply", _RecordingHandler.records)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


@test("driver handshake registers HTTP adapter and drains outbox entries")
def _(
    sse_env_fixture: Any = sse_env, handshake_fixture: Any = handshake_server
) -> None:
    env = sse_env_fixture  # type: ignore[assignment]
    endpoint, records = handshake_fixture

    response = env.client.post(
        "/k0/driver.handshake",
        json={
            "alias": "st_vector",
            "transport": "http",
            "endpoint": endpoint,
            "capabilities": ["apply"],
            "metadata": {"version": "1.0.0"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    session_id = payload["session_id"]
    assert payload["alias"] == "st_vector"
    assert payload["driver_module"] == "faiss"
    assert payload["lease_seconds"] >= 300

    pool = getattr(env.app.state, "driver_worker_pool", None)
    assert isinstance(pool, DriverWorkerPool)

    outbox_store = env.app.state.outbox_store
    entry = OutboxEntry(
        id=None,
        wal_pos=1,
        tenant_id="tenant-A",
        space_id="space-main",
        driver="st_vector",
        op_kind="UPSERT",
        payload=b"payload",
        fingerprint=compute_fingerprint("st_vector", "UPSERT", b"payload"),
        requeue_seq=0,
        retries=0,
        last_error=None,
    )
    entry_id = outbox_store.enqueue(entry)

    pool.process_driver("st_vector")

    assert outbox_store.dequeue_batch("st_vector", limit=4) == []
    assert len(records) == 1
    recorded = records[0]
    assert recorded["session"] == session_id

    body = json.loads(recorded["body"].decode("utf-8"))
    assert body["id"] == entry_id
    assert body["wal_pos"] == 1
    assert body["tenant_id"] == "tenant-A"
    assert body["space_id"] == "space-main"
    assert body["driver"] == "st_vector"
    assert body["op_kind"] == "UPSERT"
    assert body["fingerprint"] == entry.fingerprint
    assert body["retries"] == 0
    assert body["requeue_seq"] == 0
    assert body["payload_base64"] == base64.b64encode(b"payload").decode("ascii")

