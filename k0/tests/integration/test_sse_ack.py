from __future__ import annotations

import json
from typing import Any

from ward import test  # type: ignore[attr-defined]

from k0.kernel.dependencies import qos_context_dependency
from k0.qos import QoSContext, Scheduler, SchedulerProfile
from k0.uow.connection_pool import connection_scope
from tests.integration.sse_fixtures import SSETestEnv, sse_env
from tests.integration.support.environment import REPO_ROOT

SSE_ACK_EXAMPLE_PATH = (
    REPO_ROOT / "k0" / "contracts" / "jsonschema" / "examples" / "sse.ack.request.json"
)


def _load_example_payload() -> dict[str, Any]:
    return json.loads(SSE_ACK_EXAMPLE_PATH.read_text(encoding="utf-8"))


@test("sse.ack persists subscriber offsets")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    payload = _load_example_payload()

    response = env.client.post("/k0/sse.ack", json=payload)
    assert response.status_code == 204
    assert response.content == b""

    with connection_scope() as conn:
        row = conn.execute(
            (
                "SELECT subscriber_id, topic, space_id, tenant_id, offset, updated_ts "
                "FROM st_offsets"
            )
        ).fetchone()
        assert row is not None
        assert row["subscriber_id"] == payload["subscriber_id"]
        assert row["topic"] == payload["topic"]
        assert row["space_id"] == payload["space_id"]
        assert row["tenant_id"] == payload["tenant_id"]
        assert row["offset"] == payload["offset"]
        expected_ts = payload["ack_ts"].replace("Z", "+00:00")
        assert row["updated_ts"] == expected_ts


@test("sse.ack rejects invalid ack timestamps")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    payload = _load_example_payload()
    payload["ack_ts"] = "invalid-timestamp"

    response = env.client.post("/k0/sse.ack", json=payload)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "SSE_BAD_REQUEST"
    assert error["component"] == "kernel.sse"
    assert error["reason"] == "ACK_TS_INVALID"

    with connection_scope() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM st_offsets").fetchone()
        assert row is not None
        assert row["total"] == 0


@test("sse.ack enforces fanout budget")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    payload = _load_example_payload()

    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration test profile",
            port_limits={"sse": 32},
            default_port_limit=32,
        )
    )

    def qos_override() -> QoSContext:
        return QoSContext(scheduler=scheduler, fanout_budget=0, top_k_budget=8)

    env.app.dependency_overrides[qos_context_dependency] = qos_override
    try:
        response = env.client.post("/k0/sse.ack", json=payload)
        assert response.status_code == 429
        error = response.json()["error"]
        assert error["code"] == "QOS_BUDGET_EXHAUSTED"
        assert error["component"] == "kernel.qos"
        assert error["details"]["cap"] == "fanout"
        budgets = error.get("budgets", {})
        assert budgets.get("fanout") == 0
    finally:
        env.app.dependency_overrides.pop(qos_context_dependency, None)


@test("sse.ack enforces scheduler capacity limits")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    payload = _load_example_payload()

    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration test profile",
            port_limits={"sse": 0},
            default_port_limit=0,
        )
    )

    def qos_override() -> QoSContext:
        return QoSContext(scheduler=scheduler, fanout_budget=1, top_k_budget=8)

    env.app.dependency_overrides[qos_context_dependency] = qos_override
    try:
        response = env.client.post("/k0/sse.ack", json=payload)
        assert response.status_code == 429
        error = response.json()["error"]
        assert error["code"] == "QOS_BUDGET_EXHAUSTED"
        assert error["component"] == "kernel.qos"
        assert error["details"]["cap"] == "scheduler"
        assert "hint" in error
    finally:
        env.app.dependency_overrides.pop(qos_context_dependency, None)
