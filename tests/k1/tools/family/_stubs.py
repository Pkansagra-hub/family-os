"""Test doubles and stubs for the family-tool foundation."""

from __future__ import annotations

from typing import Any

from k1.tools.family.base import WriteContext
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.definition import (
    ActionSpec,
    FieldSpec,
    LLMHints,
    SSESpec,
    ToolDefinition,
)
from k1.tools.family.ports import ISsePublisher, ISyncOutbox

# ---------------------------------------------------------------------------
# PingToolService -- exercises the full Fabric -> NativeToolProvider path.
# ---------------------------------------------------------------------------


class PingToolService:
    """Minimal ``IToolService`` exercising the dispatch path."""

    DEFINITION = ToolDefinition(
        adapter_id="ping",
        version="1.0.0",
        category="diagnostic",
        summary="Echo / liveness probe for the family-tool runtime.",
        title="Ping",
        description="Diagnostic adapter used by the family-tool foundation tests.",
        entity_type="ping",
        tables_sql=(
            "CREATE TABLE IF NOT EXISTS ping_schema_version (version INTEGER PRIMARY KEY);\n"
            "CREATE TABLE IF NOT EXISTS ping_log (id TEXT PRIMARY KEY, ts INTEGER NOT NULL);\n"
        ),
        actions=[
            ActionSpec(
                name="ping",
                kind="compute",
                summary="Return pong.",
                min_band="GREEN",
                allowed_roles=["parent", "child", "guardian", "elder", "system", "guest"],
                params=[
                    FieldSpec(name="message", type="string", required=False),
                ],
                result=[
                    FieldSpec(name="pong", type="boolean", required=True),
                    FieldSpec(name="echo", type="string", required=False),
                ],
                llm=LLMHints(use_when=["Liveness probe for the runtime."]),
                sse=SSESpec(emits=["family.ping.ping.compute.v1"]),
            ),
            ActionSpec(
                name="list_pings",
                kind="read",
                summary="Return an empty list (read-path smoke test).",
                min_band="GREEN",
                allowed_roles=["parent", "guardian", "elder", "system"],
                params=[],
                result=[FieldSpec(name="items", type="array", required=True)],
            ),
        ],
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], WriteContext]] = []

    async def dispatch(
        self,
        action: str,
        params: dict[str, Any],
        ctx: WriteContext,
    ) -> dict[str, Any]:
        self.calls.append((action, params, ctx))
        if action == "ping":
            return {"pong": True, "echo": params.get("message", "")}
        if action == "list_pings":
            return {"items": [], "count": 0}
        raise ValueError(f"Unknown action {action!r}")


# ---------------------------------------------------------------------------
# Recording stubs for EventEmitter wiring.
# ---------------------------------------------------------------------------


class RecordingSsePublisher(ISsePublisher):
    """In-memory ``ISsePublisher`` that records every publish call."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, payload))


class RecordingSyncOutbox(ISyncOutbox):
    """In-memory ``ISyncOutbox`` that records every enqueue call."""

    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue(self, envelope: dict[str, Any]) -> None:
        self.enqueued.append(envelope)


class RaisingSsePublisher(ISsePublisher):
    """SSE publisher that always raises; used to verify swallow-and-log."""

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("simulated SSE failure")


class RaisingSyncOutbox(ISyncOutbox):
    """Sync outbox that always raises; used to verify swallow-and-log."""

    def enqueue(self, envelope: dict[str, Any]) -> None:
        raise RuntimeError("simulated outbox failure")


# ---------------------------------------------------------------------------
# Demo BaseToolService subclass for §E15.0.5-E15.0.10 wiring tests.
# ---------------------------------------------------------------------------


class DemoToolService(BaseToolService):
    """Minimal :class:`BaseToolService` subclass exercising the dispatch backbone."""

    DEFINITION = ToolDefinition(
        adapter_id="demo",
        version="1.0.0",
        category="diagnostic",
        summary="Demo adapter for wiring tests.",
        title="Demo",
        entity_type="demo_item",
        tables_sql=(
            "CREATE TABLE IF NOT EXISTS demo_schema_version (version INTEGER PRIMARY KEY);\n"
            "CREATE TABLE IF NOT EXISTS demo_log (id TEXT PRIMARY KEY, ts INTEGER NOT NULL);\n"
        ),
        actions=[
            ActionSpec(
                name="echo",
                kind="compute",
                summary="Echo back the message.",
                allowed_roles=["parent", "child", "guardian", "elder", "system"],
                params=[FieldSpec(name="message", type="string", required=True)],
                result=[FieldSpec(name="echo", type="string", required=True)],
            ),
            ActionSpec(
                name="record_write",
                kind="write",
                summary="Persist a row + emit an event.",
                allowed_roles=["parent", "guardian", "system"],
                min_role="parent",
                idempotent=True,
                params=[FieldSpec(name="payload", type="string", required=True)],
                result=[FieldSpec(name="id", type="string", required=True)],
                sse=SSESpec(emits=["family.demo.record_write.write.v1"]),
            ),
            ActionSpec(
                name="boom",
                kind="compute",
                summary="Raise on purpose.",
                allowed_roles=["parent", "system"],
            ),
            ActionSpec(
                name="bad_return",
                kind="compute",
                summary="Return non-dict.",
                allowed_roles=["parent", "system"],
            ),
            ActionSpec(
                name="adults_only",
                kind="read",
                summary="Adults-only read.",
                allowed_roles=["parent", "guardian", "system"],
                min_band="AMBER",
            ),
        ],
    )

    async def echo(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        return {"echo": params.get("message", "")}

    async def record_write(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        # Persist into the demo_log table to prove tables_sql ran.
        rid = f"row-{params.get('payload', '')}"
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO demo_log (id, ts) VALUES (?, strftime('%s','now'))",
                (rid,),
            )
        spec = self.DEFINITION.find_action("record_write")
        assert spec is not None
        self.emit_write(spec, {"id": rid}, ctx)
        return {"id": rid}

    async def boom(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    async def bad_return(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        return "not a dict"  # type: ignore[return-value]

    async def adults_only(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        return {"items": [], "count": 0}
