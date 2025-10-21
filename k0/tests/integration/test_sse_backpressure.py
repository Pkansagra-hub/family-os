from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from ward import test  # type: ignore[attr-defined]

from k0.storage.wal import WalEntry
from tests.integration.sse_fixtures import SSETestEnv, sse_env

_SUBSCRIBER_ID = "sub-123"
_TENANT_ID = "tenant-123"
_SPACE_ID = "space-123"
_TOPIC = "memory.story"
_SCHEMA_URI = "https://contracts.family-ai.dev/schemas/memory.story.json"
_SCHEMA_VERSION = "1.0.0"
_DEVICE_ID = "device-123"


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_events(env: SSETestEnv, count: int, commit_offset_ms: int = 0) -> None:
    wal = env.app.state.write_ahead_log
    base = datetime.now(tz=timezone.utc) + timedelta(milliseconds=commit_offset_ms)
    for index in range(count):
        commit_ts = _isoformat(base + timedelta(milliseconds=index))
        wal.append(
            WalEntry(
                tenant_id=_TENANT_ID,
                space_id=_SPACE_ID,
                topic=_TOPIC,
                envelope_json="{}",
                schema_uri=_SCHEMA_URI,
                schema_version=_SCHEMA_VERSION,
                device_id=_DEVICE_ID,
                commit_ts=commit_ts,
            )
        )


def _post_ack(env: SSETestEnv, offset: int, delta: timedelta) -> None:
    ack_ts = _isoformat(datetime.now(tz=timezone.utc) - delta)
    payload: dict[str, Any] = {
        "subscriber_id": _SUBSCRIBER_ID,
        "topic": _TOPIC,
        "space_id": _SPACE_ID,
        "tenant_id": _TENANT_ID,
        "offset": offset,
        "ack_ts": ack_ts,
    }
    response = env.client.post("/k0/sse.ack", json=payload)
    assert response.status_code == 204


def _subscribe(env: SSETestEnv) -> tuple[int, str]:
    response = env.client.get(
        "/k0/sse.subscribe",
        params={
            "topics": _TOPIC,
            "space_id": _SPACE_ID,
            "tenant_id": _TENANT_ID,
        },
        headers={"X-SSE-Subscriber": _SUBSCRIBER_ID},
    )
    return response.status_code, response.text


def _extract_event_payloads(sse_payload: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_type: str | None = None
    data_buffer: list[str] = []
    for line in sse_payload.splitlines():
        if line.startswith("event: "):
            if event_type is not None and data_buffer:
                data_str = "\n".join(data_buffer)
                events.append((event_type, json.loads(data_str)))
                data_buffer.clear()
            event_type = line[len("event: ") :].strip()
        elif line.startswith("data: "):
            data_buffer.append(line[len("data: ") :].strip())
        elif not line:
            if event_type is not None and data_buffer:
                data_str = "\n".join(data_buffer)
                events.append((event_type, json.loads(data_str)))
            event_type = None
            data_buffer = []
    if event_type is not None and data_buffer:
        data_str = "\n".join(data_buffer)
        events.append((event_type, json.loads(data_str)))
    return events


@test("sse.subscribe emits lag warning advisory when behind")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    env.app.state.observability_emitter.clear()

    _append_events(env, count=3)
    _post_ack(env, offset=0, delta=timedelta(seconds=3))

    status_code, payload = _subscribe(env)
    assert status_code == 200, payload

    events = _extract_event_payloads(payload)
    assert events
    advisory_type, advisory_payload = events[0]
    assert advisory_type == "advisory"
    assert advisory_payload["type"] == "lag-warning"
    assert advisory_payload["subscriber_id"] == _SUBSCRIBER_ID

    trace_events = [event for event in events if event[0] == "trace"]
    assert trace_events, "expected trace events to be delivered"

    obs_events = env.app.state.observability_emitter.snapshot()
    actions = {
        event.get("action")
        for event in obs_events
        if event.get("event") == "sse_backpressure"
    }
    assert "lag-warning" in actions

    registry = env.app.state.metrics_exporter.registry
    lag_count = registry.get_sample_value(
        "k0_kernel_sse_delivery_lag_seconds_count",
        {"port": "sse", "level": "warning"},
    )
    assert lag_count == 1.0
    pending_gauge = registry.get_sample_value(
        "k0_kernel_sse_pending_events",
        {"port": "sse", "level": "warning"},
    )
    assert pending_gauge is not None and pending_gauge >= 0.0


@test("sse.subscribe throttles deliveries and emits throttled advisory")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    env.app.state.observability_emitter.clear()

    _append_events(env, count=4)
    _post_ack(env, offset=0, delta=timedelta(seconds=7))

    status_code, payload = _subscribe(env)
    assert status_code == 200, payload

    events = _extract_event_payloads(payload)
    advisory = next((event for event in events if event[0] == "advisory"), None)
    assert advisory is not None
    _, advisory_payload = advisory
    assert advisory_payload["type"] == "throttled"
    assert advisory_payload.get("throttle_ratio") == 0.5

    trace_count = sum(1 for event in events if event[0] == "trace")
    assert trace_count == 2

    obs_events = env.app.state.observability_emitter.snapshot()
    actions = {
        event.get("action")
        for event in obs_events
        if event.get("event") == "sse_backpressure"
    }
    assert "throttled" in actions

    registry = env.app.state.metrics_exporter.registry
    lag_count = registry.get_sample_value(
        "k0_kernel_sse_delivery_lag_seconds_count",
        {"port": "sse", "level": "throttle"},
    )
    assert lag_count == 1.0


@test("sse.subscribe sheds connection when buffer pressure exceeds max_lag_entries")
def _(sse_env_fixture: SSETestEnv = sse_env) -> None:
    env = sse_env_fixture
    env.app.state.observability_emitter.clear()

    _append_events(env, count=5)
    _post_ack(env, offset=0, delta=timedelta(seconds=20))

    status_code, payload = _subscribe(env)
    assert status_code == 429, payload

    error = json.loads(payload)["error"]
    assert error["reason"] == "BACKPRESSURE_SHED"
    assert error["code"] == "SSE_BACKPRESSURE"

    obs_events = env.app.state.observability_emitter.snapshot()
    actions = [
        event.get("action")
        for event in obs_events
        if event.get("event") == "sse_backpressure"
    ]
    assert "shed" in actions

    registry = env.app.state.metrics_exporter.registry
    lag_count = registry.get_sample_value(
        "k0_kernel_sse_delivery_lag_seconds_count",
        {"port": "sse", "level": "shed"},
    )
    assert lag_count == 1.0
