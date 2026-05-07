"""M17.E1.I1 — Back-actor dispatch passthrough gate.

When ``allow_dispatch_passthrough`` is False (production default) and
``ToolContext.dispatch is None``, the four Back-actor capability tools
(``invoke_capability``, ``batch_invoke_capabilities``,
``spawn_via_fabric``, ``execute_workflow``) MUST refuse to run and
return a ``dispatch_not_wired`` error rather than fabricate a synthetic
``{"_poc": True, ...}`` payload.

When ``allow_dispatch_passthrough`` is True, the legacy POC stub path
is preserved for test/dev contexts that intentionally build a
ToolContext without an IDispatchPort.
"""

from __future__ import annotations

import pytest

from k1.concierge.tools.implementations import (
    ToolContext,
    execute_batch_invoke_capabilities,
    execute_execute_workflow,
    execute_invoke_capability,
    execute_spawn_via_fabric,
)


def _ctx(*, allow: bool) -> ToolContext:
    return ToolContext(
        session_manager=None,
        cognitive_trace_id="trace-test",
        actor="back",
        dispatch=None,
        allow_dispatch_passthrough=allow,
    )


# ---------------------------------------------------------------------------
# Hard-fail (production default): allow_dispatch_passthrough=False
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_fn, args",
    [
        (execute_invoke_capability, {"capability_name": "tool.send_message", "params": {}}),
        (
            execute_batch_invoke_capabilities,
            {"invocations": [{"capability_name": "tool.x", "params": {}}]},
        ),
        (execute_spawn_via_fabric, {"agent_type": "research", "task": "summarize"}),
        (execute_execute_workflow, {"workflow_id": "morning_briefing", "params": {}}),
    ],
)
async def test_dispatch_not_wired_returns_error_when_passthrough_disabled(tool_fn, args) -> None:
    ctx = _ctx(allow=False)
    result = await tool_fn(args, ctx)

    assert result.status == "error"
    assert result.error is not None
    assert result.error.startswith("dispatch_not_wired")


# ---------------------------------------------------------------------------
# Legacy POC stub: allow_dispatch_passthrough=True
# ---------------------------------------------------------------------------


async def test_invoke_capability_poc_stub_when_passthrough_enabled() -> None:
    ctx = _ctx(allow=True)
    result = await execute_invoke_capability(
        {"capability_name": "tool.send_message", "params": {"to": "x"}}, ctx
    )

    assert result.status == "ok"
    assert result.data["result"]["_poc"] is True
    assert result.data["result"]["capability"] == "tool.send_message"


async def test_spawn_via_fabric_poc_stub_when_passthrough_enabled() -> None:
    ctx = _ctx(allow=True)
    result = await execute_spawn_via_fabric({"agent_type": "research", "task": "summarize"}, ctx)

    assert result.status == "ok"
    assert result.data["status"] == "spawned"
    assert result.data["agent_id"].startswith("agent-")


async def test_execute_workflow_poc_stub_when_passthrough_enabled() -> None:
    ctx = _ctx(allow=True)
    result = await execute_execute_workflow({"workflow_id": "morning_briefing", "params": {}}, ctx)

    assert result.status == "ok"
    assert result.data["status"] == "completed"
    assert result.data["result"]["_poc"] is True
