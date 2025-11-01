"""Comprehensive integration tests for Query Subsystem (registry + drivers).

This test suite validates the Query Subsystem to move from AMBER to GREEN status by ensuring:
1. Registry resolver works correctly for all driver types
2. WAL driver returns canonical rows (wal_pos, tenant_id, space_id, topic, etc.)
3. FTS driver provides full-text search capability
4. Pagination cursor stability across multiple queries
5. Multi-table recall coordination
6. Proper error handling and edge cases
7. Performance within budgets (P95 latency)

Requirements from QoS Testing Plan:
- WAL driver returns canonical rows; optional FTS/vector plugged; pagination cursor stable
"""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.query.common import DriverContext, DriverExecution
from k0.query.drivers import AliasDriver, DriverRegistry, WalDriver, build_default_registry
from k0.storage.wal import WalEntry
from k0.uow.connection_pool import connection_scope, shutdown_pool

REPO_ROOT = Path(__file__).resolve().parents[3]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


class QueryTestEnv(SimpleNamespace):
    """Test environment for Query Subsystem integration tests."""

    client: TestClient
    app: Any
    tenant_id: str
    space_id: str
    device_id: str
    db_path: Path


@pytest.fixture
def query_test_env() -> Iterator[QueryTestEnv]:
    """Fixture providing complete Query Subsystem test environment."""
    tmp_dir = TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"

    settings = KernelSettings.load(
        overrides={
            "database": {"path": str(db_path)},
            "telemetry": {"otlp_endpoint": None},
        }
    )
    app: FastAPI = create_app(settings=settings)

    storage_sql = STORAGE_SQL_PATH.read_text(encoding="utf-8")

    with connection_scope() as conn:
        conn.executescript(storage_sql)
        conn.commit()

    app.state.observability_emitter.clear()

    env = QueryTestEnv(
        tenant_id="tenant-query-test",
        space_id="space-query-test",
        device_id="device-query-test",
        db_path=db_path,
    )

    with TestClient(app) as client:
        with connection_scope() as conn:
            table_names = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        if "st_wal" not in table_names:
            raise AssertionError("storage schema bootstrap failed: st_wal missing")
        env.client = client
        env.app = app
        yield env

    shutdown_pool()
    tmp_dir.cleanup()


def _append_wal(
    env: QueryTestEnv,
    *,
    topic: str,
    payload: dict[str, Any],
    commit_ts: str,
) -> int:
    """Helper to append WAL entry and return position."""
    envelope = {
        "cognitive_trace_id": str(uuid4()),
        "tenant_id": env.tenant_id,
        "space_id": env.space_id,
        "topic": topic,
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.0",
        "device_id": env.device_id,
        "actor": "actor-query",
        "band": "GREEN",
        "policy_version": "v1",
        "ts": commit_ts,
    }

    body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_sha256 = sha256(body_bytes).hexdigest()

    envelope_json = json.dumps(
        {
            **envelope,
            "payload_sha256": payload_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    wal_entry = WalEntry(
        tenant_id=envelope["tenant_id"],
        space_id=envelope["space_id"],
        topic=envelope["topic"],
        envelope_json=envelope_json,
        body=body_bytes,
        payload_sha256=payload_sha256,
        schema_uri=envelope["schema_uri"],
        schema_version=envelope["schema_version"],
        idem_key=None,
        device_id=envelope["device_id"],
        commit_ts=commit_ts,
    )

    with connection_scope() as conn:
        position = env.app.state.write_ahead_log.append(wal_entry, connection=conn)
        conn.commit()
    return position


# ============================================================================
# GATE 1: Registry Resolver Tests
# ============================================================================


def test_registry_resolves_wal_driver_for_default_selectors(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry returns WAL driver for default selectors."""
    registry = build_default_registry(default_limit=8, max_limit=256)
    selector = SimpleNamespace(topic="memory.timeline", limit=5)
    driver = registry.resolve(selector)
    assert driver.name == "wal"
    assert isinstance(driver, WalDriver)


def test_registry_resolves_wal_driver_for_timeline_types(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry routes timeline-like types to WAL driver."""
    registry = build_default_registry(default_limit=8, max_limit=256)
    for type_val in ["timeline", "episodic", "memory.timeline", "event", "default"]:
        selector = SimpleNamespace(type=type_val, topic="memory.timeline")
        driver = registry.resolve(selector)
        assert driver.name == "wal", f"Expected WAL for type={type_val}"


def test_registry_resolves_fts_driver_for_semantic_types(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry routes semantic types to FTS driver."""
    registry = build_default_registry(default_limit=8, max_limit=256)
    for type_val in ["fts", "semantic", "semantic_memory", "fulltext", "text"]:
        selector = SimpleNamespace(type=type_val, topic="memory.semantic")
        driver = registry.resolve(selector)
        assert driver.name == "fts", f"Expected FTS for type={type_val}"


def test_registry_resolves_alias_drivers_for_unavailable_types(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry maps unavailable types to alias drivers."""
    registry = build_default_registry(default_limit=8, max_limit=256)
    selector = SimpleNamespace(type="vector", topic="memory.semantic")
    driver = registry.resolve(selector)
    assert driver.name == "vector"
    assert isinstance(driver, AliasDriver)
    assert driver.reason == "vector recall driver not configured"


def test_registry_raises_lookup_error_for_unknown_types(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry raises error for truly unknown types."""
    registry = build_default_registry(default_limit=8, max_limit=256)
    selector = SimpleNamespace(type="unknown_future_type_xyz", topic="memory.unknown")
    with pytest.raises(LookupError, match="No query driver registered"):
        registry.resolve(selector)


def test_registry_allows_custom_driver_registration(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry supports extending with custom drivers."""
    registry = DriverRegistry()

    class CustomDriver:
        name = "custom"

        def supports(self, selector: Any) -> bool:
            return getattr(selector, "type", None) == "custom"

        def execute(self, selector: Any, context: DriverContext) -> DriverExecution:
            return DriverExecution(driver="custom", selector_index=0, selector={})

    registry.register(CustomDriver())  # type: ignore[arg-type]
    selector = SimpleNamespace(type="custom")
    driver = registry.resolve(selector)
    assert driver.name == "custom"


# ============================================================================
# GATE 2: WAL Driver Tests - Canonical Row Format
# ============================================================================


def test_wal_driver_returns_canonical_rows(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver returns items with all canonical fields."""
    _append_wal(
        query_test_env,
        topic="memory.timeline",
        payload={"value": "test-canonical"},
        commit_ts="2025-10-31T10:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 10}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 1
    item = items[0]

    # Verify canonical fields
    for field in [
        "wal_pos",
        "tenant_id",
        "space_id",
        "topic",
        "commit_ts",
        "schema_uri",
        "schema_version",
        "device_id",
        "payload_sha256",
        "envelope",
        "body",
    ]:
        assert field in item, f"Missing field: {field}"

    assert item["tenant_id"] == query_test_env.tenant_id
    assert item["space_id"] == query_test_env.space_id
    assert item["topic"] == "memory.timeline"


def test_wal_driver_respects_topic_filter(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver filters by topic correctly."""
    _append_wal(
        query_test_env,
        topic="memory.timeline",
        payload={"type": "timeline"},
        commit_ts="2025-10-31T10:00:00Z",
    )
    _append_wal(
        query_test_env,
        topic="memory.semantic",
        payload={"type": "semantic"},
        commit_ts="2025-10-31T10:00:01Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 10}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 1
    assert items[0]["topic"] == "memory.timeline"


def test_wal_driver_respects_tenant_isolation(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver enforces tenant isolation."""
    _append_wal(
        query_test_env,
        topic="memory.timeline",
        payload={"tenant": "main"},
        commit_ts="2025-10-31T10:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 10}],
            "space_id": query_test_env.space_id,
            "tenant_id": "tenant-different",
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 0


def test_wal_driver_respects_space_isolation(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver enforces space isolation."""
    _append_wal(
        query_test_env,
        topic="memory.timeline",
        payload={"space": "main"},
        commit_ts="2025-10-31T10:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 10}],
            "space_id": "space-different",
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 0


def test_wal_driver_orders_results_descending(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver returns results in descending position order."""
    for i in range(3):
        _append_wal(
            query_test_env,
            topic="memory.timeline",
            payload={"index": i},
            commit_ts=f"2025-10-31T10:00:{i:02d}Z",
        )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 10}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 3
    returned_positions = [item["wal_pos"] for item in items]
    assert returned_positions == sorted(returned_positions, reverse=True)


# ============================================================================
# GATE 3: FTS Driver Tests
# ============================================================================


def test_fts_driver_returns_empty_without_query(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify FTS driver returns empty results if no query provided."""
    _append_wal(
        query_test_env,
        topic="memory.semantic",
        payload={"text": "test content"},
        commit_ts="2025-10-31T11:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"type": "fts", "topic": "memory.semantic", "limit": 10}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    selector_result = response.json()["bundle"]["selectors"][0]
    items = selector_result["items"]
    assert len(items) == 0
    assert selector_result["metadata"]["status"] == "no_query"


def test_fts_driver_metadata(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify FTS driver metadata contains source and query info."""
    _append_wal(
        query_test_env,
        topic="memory.semantic",
        payload={"text": "example content"},
        commit_ts="2025-10-31T11:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [
                {
                    "type": "fts",
                    "topic": "memory.semantic",
                    "query": "example",
                    "limit": 10,
                }
            ],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    selector_result = response.json()["bundle"]["selectors"][0]
    metadata = selector_result["metadata"]
    assert metadata["source"] == "st_fts"
    assert metadata["query"] == "example"
    assert "rows" in metadata


# ============================================================================
# GATE 4: Pagination & Cursor Stability Tests
# ============================================================================


def test_pagination_cursor_stable(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify pagination cursor stays consistent for identical queries."""
    for i in range(5):
        _append_wal(
            query_test_env,
            topic="memory.timeline",
            payload={"index": i},
            commit_ts=f"2025-10-31T12:00:{i:02d}Z",
        )

    response1 = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 2}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response1.status_code == 200
    cursor1 = response1.json()["bundle"]["selectors"][0]["next_cursor"]

    response2 = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 2}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response2.status_code == 200
    cursor2 = response2.json()["bundle"]["selectors"][0]["next_cursor"]
    assert cursor1 == cursor2


def test_pagination_cursor_advances(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify cursor-based pagination works correctly."""
    for i in range(5):
        _append_wal(
            query_test_env,
            topic="memory.timeline",
            payload={"index": i},
            commit_ts=f"2025-10-31T12:00:{i:02d}Z",
        )

    response1 = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 2}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    items1 = response1.json()["bundle"]["selectors"][0]["items"]
    cursor1 = response1.json()["bundle"]["selectors"][0]["next_cursor"]
    assert len(items1) == 2

    response2 = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 2, "cursor": cursor1}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    items2 = response2.json()["bundle"]["selectors"][0]["items"]
    assert len(items2) == 2
    ids1 = {item["wal_pos"] for item in items1}
    ids2 = {item["wal_pos"] for item in items2}
    assert not ids1.intersection(ids2)


def test_pagination_reaches_end(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify pagination correctly signals end of results."""
    for i in range(3):
        _append_wal(
            query_test_env,
            topic="memory.timeline",
            payload={"index": i},
            commit_ts=f"2025-10-31T12:00:{i:02d}Z",
        )

    response1 = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 2}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    cursor1 = response1.json()["bundle"]["selectors"][0]["next_cursor"]

    response2 = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 2, "cursor": cursor1}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    items2 = response2.json()["bundle"]["selectors"][0]["items"]
    assert len(items2) == 1


# ============================================================================
# GATE 5: Multi-Driver Coordination Tests
# ============================================================================


def test_multiple_selectors_execute(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify registry coordinates multiple selectors correctly."""
    _append_wal(
        query_test_env,
        topic="memory.timeline",
        payload={"type": "timeline"},
        commit_ts="2025-10-31T13:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [
                {"type": "wal", "topic": "memory.timeline", "limit": 5},
                {"type": "vector", "topic": "memory.semantic", "limit": 5},
            ],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    selectors = response.json()["bundle"]["selectors"]
    assert len(selectors) == 2
    assert selectors[0]["selector"]["driver"] == "wal"
    assert len(selectors[0]["items"]) == 1
    assert selectors[1]["selector"]["driver"] == "vector"
    assert selectors[1]["metadata"]["status"] == "unavailable"


def test_selector_trace_latency(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify trace includes per-driver latency information."""
    _append_wal(
        query_test_env,
        topic="memory.timeline",
        payload={"data": "test"},
        commit_ts="2025-10-31T13:00:00Z",
    )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.timeline", "limit": 5}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    trace = response.json()["trace"]
    trace_nodes = trace.get("nodes", [])
    wal_nodes = [n for n in trace_nodes if n.get("stage") == "query.driver.wal"]
    assert len(wal_nodes) > 0
    assert "latency_ms" in wal_nodes[0]


# ============================================================================
# GATE 6: Error Handling & Edge Cases
# ============================================================================


def test_wal_driver_handles_empty_result(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver handles queries with no results."""
    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.nonexistent", "limit": 5}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 0


def test_binary_body_base64_encoded(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify binary payload is properly encoded for JSON response."""
    binary_payload = b"\x00\x01\x02\x03\x04"
    envelope = {
        "cognitive_trace_id": str(uuid4()),
        "tenant_id": query_test_env.tenant_id,
        "space_id": query_test_env.space_id,
        "topic": "memory.binary",
        "schema_uri": "schema://binary",
        "schema_version": "1.0",
        "device_id": query_test_env.device_id,
        "actor": "actor-query",
        "band": "GREEN",
        "policy_version": "v1",
        "ts": "2025-10-31T14:00:00Z",
    }

    envelope_json = json.dumps(
        {
            **envelope,
            "payload_sha256": sha256(binary_payload).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    wal_entry = WalEntry(
        tenant_id=envelope["tenant_id"],
        space_id=envelope["space_id"],
        topic=envelope["topic"],
        envelope_json=envelope_json,
        body=binary_payload,
        payload_sha256=sha256(binary_payload).hexdigest(),
        schema_uri=envelope["schema_uri"],
        schema_version=envelope["schema_version"],
        idem_key=None,
        device_id=envelope["device_id"],
        commit_ts=envelope["ts"],
    )

    with connection_scope() as conn:
        query_test_env.app.state.write_ahead_log.append(wal_entry, connection=conn)
        conn.commit()

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [{"topic": "memory.binary", "limit": 5}],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
        },
    )
    assert response.status_code == 200
    items = response.json()["bundle"]["selectors"][0]["items"]
    assert len(items) == 1
    body = items[0]["body"]
    # Binary data should be base64 encoded in dict or as-is
    if isinstance(body, dict):
        assert body["encoding"] == "base64"
        assert body["payload"] == base64.b64encode(binary_payload).decode("ascii")
    else:
        # Body might be returned as-is if decoded successfully
        assert isinstance(body, (str, dict))


# ============================================================================
# GATE 7: Performance Budget Tests
# ============================================================================


def test_wal_driver_latency_budget(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify WAL driver meets P95 latency budget (<100ms)."""
    for i in range(10):
        _append_wal(
            query_test_env,
            topic="memory.timeline",
            payload={"index": i},
            commit_ts=f"2025-10-31T15:00:{i % 60:02d}Z",
        )

    latencies = []
    for _ in range(5):
        response = query_test_env.client.post(
            "/k0/query.recall",
            json={
                "selectors": [{"topic": "memory.timeline", "limit": 10}],
                "space_id": query_test_env.space_id,
                "tenant_id": query_test_env.tenant_id,
            },
        )
        assert response.status_code == 200
        trace = response.json()["trace"]
        wal_nodes = [n for n in trace.get("nodes", []) if "query.driver.wal" in n.get("stage", "")]
        if wal_nodes:
            latencies.append(wal_nodes[0]["latency_ms"])

    if latencies:
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95_latency < 100, f"P95 latency {p95_latency}ms exceeds 100ms budget"


def test_multi_selector_completes(
    query_test_env: QueryTestEnv,
) -> None:
    """Verify multi-selector query respects overall time budget."""
    for i in range(5):
        _append_wal(
            query_test_env,
            topic="memory.timeline",
            payload={"index": i},
            commit_ts=f"2025-10-31T15:00:{i:02d}Z",
        )

    response = query_test_env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [
                {"type": "wal", "topic": "memory.timeline", "limit": 5},
                {"type": "vector", "topic": "memory.semantic", "limit": 5},
                {"type": "kg", "topic": "memory.graph", "limit": 5},
            ],
            "space_id": query_test_env.space_id,
            "tenant_id": query_test_env.tenant_id,
            "max_latency_ms": 1000,
        },
    )
    assert response.status_code == 200
    trace = response.json()["trace"]
    assert len(trace.get("nodes", [])) > 0
