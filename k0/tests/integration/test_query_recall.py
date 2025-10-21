from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, cast
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from ward import fixture, test  # type: ignore[attr-defined]

from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.kernel.dependencies import qos_context_dependency
from k0.policy.pep_syscall import Obligation, PolicyDecision
from k0.qos import QoSContext, Scheduler, SchedulerProfile
from k0.storage.wal import WalEntry
from k0.uow.connection_pool import connection_scope, shutdown_pool

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


class QueryTestEnv(SimpleNamespace):
    client: TestClient
    app: Any
    tenant_id: str
    space_id: str
    device_id: str


@fixture
def query_env() -> Iterator[QueryTestEnv]:
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

    async def _ensure_storage_schema() -> None:
        with connection_scope() as conn:
            conn.executescript(storage_sql)
            conn.commit()

        add_event_handler = cast(
            Callable[[str, Callable[..., Any]], None],
            getattr(app, "add_event_handler"),
        )
        add_event_handler("startup", _ensure_storage_schema)

    with connection_scope() as conn:
        conn.executescript(storage_sql)
        conn.commit()

    app.state.observability_emitter.clear()

    env = QueryTestEnv(
        tenant_id="tenant-alpha",
        space_id="space-main",
        device_id="device-query-1",
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

    body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
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


@test("query.recall returns WAL slices limited by selector limit")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    for index in range(3):
        _append_wal(
            env,
            topic="memory.timeline",
            payload={"value": index},
            commit_ts=f"2025-09-28T12:00:{index:02d}Z",
        )

    response = env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [
                {
                    "topic": "memory.timeline",
                    "limit": 2,
                }
            ],
            "space_id": env.space_id,
            "tenant_id": env.tenant_id,
        },
    )
    assert response.status_code == 200
    payload = response.json()

    selectors = payload["bundle"]["selectors"]
    assert len(selectors) == 1
    selector_details = selectors[0]["selector"]
    assert selector_details["driver"] == "wal"
    assert selector_details["index"] == 0
    items = selectors[0]["items"]
    assert len(items) == 2

    wal_positions = [item["wal_pos"] for item in items]
    assert wal_positions == sorted(wal_positions, reverse=True)

    expected_fanout_remaining = max(0, int(env.app.state.settings.qos.fanout_max) - 1)
    assert payload["budgets"]["fanout"] == expected_fanout_remaining
    assert payload["budgets"]["time_slice"] >= 0
    assert payload["trace"]["selectors_executed"] == 1
    assert payload["trace"]["mode"] == "batch"

    registry = env.app.state.metrics_exporter.registry
    latency_count = registry.get_sample_value(
        "k0_kernel_http_request_latency_seconds_count",
        {
            "route": "/k0/query.recall",
            "method": "POST",
            "operation": "query",
        },
    )
    assert latency_count == 1.0
    availability_counter = registry.get_sample_value(
        "k0_kernel_http_requests_total",
        {
            "route": "/k0/query.recall",
            "method": "POST",
            "status": "200",
            "outcome": "success",
            "operation": "query",
        },
    )
    assert availability_counter == 1.0


@test("query.recall returns 429 when fanout budget is exhausted")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration test profile",
            port_limits={"query": 8},
            default_port_limit=8,
        )
    )

    def qos_override() -> QoSContext:
        return QoSContext(scheduler=scheduler, fanout_budget=1, top_k_budget=8)

    env.app.dependency_overrides[qos_context_dependency] = qos_override

    try:
        response = env.client.post(
            "/k0/query.recall",
            json={
                "selectors": [
                    {"topic": "memory.timeline", "limit": 1},
                    {"topic": "memory.timeline", "limit": 1},
                ],
                "space_id": env.space_id,
            },
        )
        assert response.status_code == 429
        payload = response.json()
        error = payload["error"]
        assert error["code"] == "QOS_BUDGET_EXHAUSTED"
        assert error["component"] == "kernel.qos"
        assert error["details"]["cap"] == "fanout"

        registry = env.app.state.metrics_exporter.registry
        fanout_counter = registry.get_sample_value(
            "k0_kernel_http_requests_total",
            {
                "route": "/k0/query.recall",
                "method": "POST",
                "status": "429",
                "outcome": "error",
                "operation": "query",
            },
        )
        assert fanout_counter == 1.0
    finally:
        env.app.dependency_overrides.pop(qos_context_dependency, None)


@test("query.recall caps results to remaining top-k budget")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration test profile",
            port_limits={"query": 8},
            default_port_limit=8,
        )
    )

    def qos_override() -> QoSContext:
        return QoSContext(scheduler=scheduler, fanout_budget=2, top_k_budget=2)

    env.app.dependency_overrides[qos_context_dependency] = qos_override

    try:
        for index in range(3):
            _append_wal(
                env,
                topic="memory.timeline",
                payload={"value": index},
                commit_ts=f"2025-09-28T13:00:{index:02d}Z",
            )

        response = env.client.post(
            "/k0/query.recall",
            json={
                "selectors": [
                    {
                        "topic": "memory.timeline",
                        "limit": 5,
                    }
                ],
                "space_id": env.space_id,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        items = payload["bundle"]["selectors"][0]["items"]
        assert len(items) == 2
        assert payload["budgets"]["fanout"] == 1
    finally:
        env.app.dependency_overrides.pop(qos_context_dependency, None)


@test("query.recall selects semantic driver stub")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    response = env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [
                {
                    "type": "semantic",
                    "topic": "memory.semantic",
                    "limit": 5,
                }
            ],
            "space_id": env.space_id,
            "tenant_id": env.tenant_id,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    selector_payload = payload["bundle"]["selectors"][0]
    assert selector_payload["selector"]["driver"] == "semantic"
    assert selector_payload["items"] == []
    metadata = selector_payload.get("metadata", {})
    assert metadata.get("status") == "unavailable"


@test("query.recall streams results when stream flag set")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    for index in range(2):
        _append_wal(
            env,
            topic="memory.timeline",
            payload={"value": index},
            commit_ts=f"2025-09-28T14:00:{index:02d}Z",
        )

    request_payload: Dict[str, Any] = {
        "selectors": [
            {
                "topic": "memory.timeline",
                "limit": 1,
            }
        ],
        "space_id": env.space_id,
        "tenant_id": env.tenant_id,
    }

    with env.client.stream(
        "POST",
        "/k0/query.recall?stream=1",
        json=request_payload,
    ) as response:
        assert response.status_code == 200
        assert response.headers.get("X-Query-Response-Mode") == "stream"
        lines = [
            line.decode("utf-8") if isinstance(line, bytes) else line
            for line in response.iter_lines()
        ]

    assert any(line.startswith("event: trace") for line in lines)
    assert any(line.startswith("event: selector") for line in lines)
    budgets_lines = [line for line in lines if line.startswith("event: budgets")]
    assert budgets_lines, "Expected budgets event in SSE stream"

    data_lines: List[Any] = [
        json.loads(line.split("data: ", 1)[1])
        for line in lines
        if line.startswith("data: ")
    ]
    stream_trace_candidates: List[Dict[str, Any]] = []
    for data in data_lines:
        if not isinstance(data, dict):
            continue
        typed_data = cast(Dict[str, Any], data)
        if typed_data.get("mode") == "stream":
            stream_trace_candidates.append(typed_data)
    assert stream_trace_candidates, "Expected stream trace payload in SSE output"
    stream_trace = stream_trace_candidates[0]
    trace_nodes = cast(List[Dict[str, Any]], stream_trace.get("nodes", []))
    assert any(
        isinstance(node, dict) and node.get("stage") == "query.driver.wal"
        for node in trace_nodes
    )


@test("query.recall denies requests for blocked policy bands")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    response = env.client.post(
        "/k0/query.recall",
        json={
            "selectors": [
                {
                    "topic": "memory.timeline",
                    "limit": 1,
                }
            ],
            "space_id": env.space_id,
            "tenant_id": env.tenant_id,
            "qos_hints": {"band": "RED"},
        },
    )
    assert response.status_code == 403
    payload = response.json()
    error = payload["error"]
    assert error["code"] == "PEP_DENY"
    assert error["component"] == "kernel.policy"
    assert error["reason"] == "BAND_BLOCKED"


@test("query.recall applies policy tightening obligations when present")
def _(query_env_obj: Any = query_env) -> None:
    env = cast(QueryTestEnv, query_env_obj)

    _append_wal(
        env,
        topic="memory.timeline",
        payload={"value": 1},
        commit_ts="2025-09-28T16:00:00Z",
    )

    obligation = Obligation(
        name="kernel.qos.tighten",
        details={
            "fanout": "1",
            "top_k": "1",
            "time_slice_ms": "42",
        },
    )
    decision = PolicyDecision(admit=True, obligations=(obligation,))

    with patch("k0.ports.query.evaluate_envelope", return_value=decision):
        response = env.client.post(
            "/k0/query.recall",
            json={
                "selectors": [
                    {
                        "topic": "memory.timeline",
                        "limit": 1,
                    }
                ],
                "space_id": env.space_id,
                "tenant_id": env.tenant_id,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    policy_trace = payload["trace"].get("policy", {})
    assert policy_trace.get("decision") == "ADMIT"
    tightening_trace = policy_trace.get("tightening", {})
    assert tightening_trace.get("time_slice_ms") == 42
    assert tightening_trace.get("fanout") == 1

    budgets_tightening = payload["budgets"].get("tightening", {})
    assert budgets_tightening.get("fanout") == 1
    assert budgets_tightening.get("top_k") == 1
