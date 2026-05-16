"""M2-L9 live-kernel SinkBridgeClient round-trip through LocalOutbox probe.

Covers kernel sweep row M2-L9 (MESSAGE-FLOW / I2.7.2, I2.7.4):

    In SINK mode (``bridge_enabled=True``, no ``k0_endpoint``), calling
    ``SinkBridgeClient.submit_command(topic, body)`` must:
      - enqueue the command to ``LocalOutbox`` (SQLite WAL)
      - NOT make any HTTP requests
      - produce a PENDING row queryable via ``outbox.list_pending()``
      - serialise the body faithfully (round-trip JSON check)

Boot Recipe — SINK mode
-----------------------
``KernelConfig(bridge_enabled=True)`` without ``k0_endpoint`` → ``SinkBridgeAdapter``
is selected at S4. ``SinkBridgeAdapter`` wraps ``SinkBridgeClient`` +
``LocalOutbox``.  ``SinkBridgeClient`` always reports ``is_connected() = False``
because K0 is unreachable.

Object graph in SINK mode
--------------------------
``svc._bridge``                 → ``SinkBridgeAdapter``
``svc._bridge.get_client()``    → ``SinkBridgeClient``
``svc._bridge._outbox``         → ``LocalOutbox`` (SQLite at ``bridge_outbox_path``)

I2.7.4 context
--------------
MS-3c shipped: ``SinkBridgeClient.recall_request_v1`` is ``None`` (placeholder
for the codegen-generated query client). The legacy ``IKernelQueryPort`` /
``QueryEnvelope`` / ``RecallBundle`` types were deleted. This test asserts
``recall_request_v1 is None`` so any accidental re-addition of a live value
will be caught.

Test coverage
-------------
| # | Assertion | Tracing ref | Expected |
|---|-----------|-------------|---------|
| 1 | ``svc._bridge`` is ``SinkBridgeAdapter`` in SINK mode | I2.7.2 | GREEN |
| 2 | ``svc._bridge.get_client()`` is ``SinkBridgeClient`` | I2.7.2 | GREEN |
| 3 | ``client.is_connected()`` is False | I2.7.2 | GREEN |
| 4 | ``submit_command`` enqueues; ``outbox.pending_count() == 1`` | I2.7.2 | GREEN |
| 5 | Enqueued row topic matches submitted topic | I2.7.2 | GREEN |
| 6 | Enqueued row status is PENDING | I2.7.2 | GREEN |
| 7 | Enqueued envelope_json body round-trips faithfully | I2.7.2 | GREEN |
| 8 | ``submit_command`` twice → pending_count == 2 | I2.7.2 | GREEN |
| 9 | ``recall_request_v1`` is None (MS-3c shipped, I2.7.4) | I2.7.4 | GREEN |
| 10 | ``sse`` is None (MS-3d shipped, I2.7.4) | I2.7.4 | GREEN |
| 11 | OfflineBridgeAdapter.get_client() returns None in OFFLINE mode | I2.7.2 neg | GREEN |
| 12 | No asyncio task leaks | acceptance gate 3 | GREEN |
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from bridge.client import SinkBridgeClient
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.adapters.bridge_adapter import OfflineBridgeAdapter, SinkBridgeAdapter
from k1.kernel.service import KernelService

pytestmark = pytest.mark.integration


# ── helpers ──────────────────────────────────────────────────────────────────


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path) -> KernelConfig:
    """Recipe A — bridge offline (bridge_enabled=False)."""
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=False,
        bridge_offline_ok=True,
        otel_enabled=False,
        enable_hitl=False,
        enable_hil_service=False,
        enable_self_model=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


def _recipe_sink(tmp_path: Path) -> KernelConfig:
    """Recipe SINK — bridge_enabled=True, no k0_endpoint → SinkBridgeAdapter."""
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=True,  # ← enables SINK mode
        bridge_offline_ok=True,
        k0_endpoint="",  # ← no endpoint → SinkBridgeAdapter (not LiveBridgeAdapter)
        otel_enabled=False,
        enable_hitl=False,
        enable_hil_service=False,
        enable_self_model=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


# ── SINK mode adapter identity probe ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l9_sink_mode_bridge_adapter_identity(tmp_path: Path) -> None:
    """svc._bridge is SinkBridgeAdapter and get_client() is SinkBridgeClient.

    PORT-IDENTITY sub-check for M2-L9: confirms SINK mode is selected correctly
    at S4 of startup() when bridge_enabled=True and k0_endpoint is empty.
    """
    svc = KernelService(config=_recipe_sink(tmp_path))
    await svc.startup()

    # ── 1. svc._bridge is SinkBridgeAdapter ──────────────────────────────────
    assert isinstance(svc._bridge, SinkBridgeAdapter), (
        f"Expected SinkBridgeAdapter, got {type(svc._bridge).__name__!r}. "
        "SINK mode not selected — check bridge_enabled=True + empty k0_endpoint."
    )

    # ── 2. get_client() returns SinkBridgeClient ──────────────────────────────
    client = svc._bridge.get_client()
    assert isinstance(
        client, SinkBridgeClient
    ), f"Expected SinkBridgeClient, got {type(client).__name__!r}"

    # ── 3. is_connected() is False ────────────────────────────────────────────
    assert (
        client.is_connected() is False
    ), "SinkBridgeClient.is_connected() must always return False — K0 unreachable in SINK mode"

    await svc.shutdown()


# ── submit_command round-trip probe ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l9_submit_command_enqueues_to_outbox(tmp_path: Path) -> None:
    """submit_command enqueues a PENDING row in LocalOutbox (I2.7.2).

    No HTTP is made (SINK). The command is durable in SQLite WAL.
    The envelope_json round-trips: body fields survive serialisation.
    """
    svc = KernelService(config=_recipe_sink(tmp_path))
    baseline_tasks = _active_task_snapshot()
    await svc.startup()

    client = svc._bridge.get_client()
    outbox = svc._bridge._outbox

    topic = "memory.write.v1"
    body = {"text": "hello from M2-L9", "session_id": "m2l9-session", "ts": 1234567890}

    # ── 4. submit_command → pending_count == 1 ────────────────────────────────
    await client.submit_command(topic, body)
    assert (
        outbox.pending_count() == 1
    ), f"Expected 1 pending row after submit_command; got {outbox.pending_count()}"

    # ── 5. Topic matches ──────────────────────────────────────────────────────
    rows = outbox.list_pending(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row.topic == topic, f"Outbox row topic is {row.topic!r}, expected {topic!r}"

    # ── 6. Status is PENDING ─────────────────────────────────────────────────
    assert row.status == "PENDING", f"Outbox row status is {row.status!r}, expected 'PENDING'"

    # ── 7. envelope_json round-trip ───────────────────────────────────────────
    parsed = json.loads(row.envelope_json)
    assert (
        parsed.get("topic") == topic
    ), f"envelope_json.topic = {parsed.get('topic')!r}, expected {topic!r}"
    assert parsed.get("body") == body, (
        f"envelope_json.body does not match submitted body.\n"
        f"  submitted: {body}\n"
        f"  recovered: {parsed.get('body')}"
    )

    await svc.shutdown()

    # ── 12. No task leaks ─────────────────────────────────────────────────────
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert not leaked, f"Task leak: {[t.get_name() for t in leaked]}"


# ── multiple submit probe ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l9_multiple_submits_accumulate_in_outbox(tmp_path: Path) -> None:
    """Each submit_command call appends a new PENDING row — no deduplication.

    The outbox is a WAL queue, not a dedup cache. Multiple identical
    commands must each produce a distinct row.
    """
    svc = KernelService(config=_recipe_sink(tmp_path))
    await svc.startup()

    client = svc._bridge.get_client()
    outbox = svc._bridge._outbox

    topic = "memory.write.v1"
    body = {"text": "duplicate command test"}

    # ── 8. Two submits → pending_count == 2 ──────────────────────────────────
    await client.submit_command(topic, body)
    await client.submit_command(topic, body)

    assert (
        outbox.pending_count() == 2
    ), f"Expected 2 pending rows after 2 submit_command calls; got {outbox.pending_count()}"

    rows = outbox.list_pending(limit=10)
    assert len(rows) == 2
    # Both rows have distinct ids (auto-increment)
    assert rows[0].id != rows[1].id, "Duplicate rows have the same id — insert not atomic"

    await svc.shutdown()


# ── MS-3c / MS-3d surface placeholders probe (I2.7.4) ────────────────────────


@pytest.mark.asyncio
async def test_m2_l9_ms3_surface_placeholders_are_none(tmp_path: Path) -> None:
    """recall_request_v1 and sse are None — MS-3c and MS-3d codegen shipped (I2.7.4).

    The legacy IKernelQueryPort / QueryEnvelope / RecallBundle hand-written
    types were deleted and replaced by codegen in bridge/_generated/k1/query/.
    Until the generated clients are wired, SinkBridgeClient keeps these as
    None class attributes.  Any non-None value means a stale hand-coded
    surface crept back in.
    """
    svc = KernelService(config=_recipe_sink(tmp_path))
    await svc.startup()

    client = svc._bridge.get_client()

    # ── 9. recall_request_v1 is None (MS-3c placeholder) ─────────────────────
    assert client.recall_request_v1 is None, (
        f"SinkBridgeClient.recall_request_v1 is {client.recall_request_v1!r}, expected None. "
        "A hand-coded legacy query surface may have been re-added (I2.7.4 regression)."
    )

    # ── 10. sse is None (MS-3d placeholder) ──────────────────────────────────
    assert client.sse is None, (
        f"SinkBridgeClient.sse is {client.sse!r}, expected None. "
        "A hand-coded legacy SSE surface may have been re-added (I2.7.4 regression)."
    )

    await svc.shutdown()


# ── offline mode negative probe ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m2_l9_offline_mode_get_client_returns_none(tmp_path: Path) -> None:
    """Recipe A (bridge_enabled=False) → OfflineBridgeAdapter.get_client() is None.

    Negative baseline: in offline mode, no SinkBridgeClient exists and no
    outbox is created.  Any caller that skips the is_connected() check will
    get an immediate AttributeError on None — the correct loud failure.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    await svc.startup()

    # ── 11. Offline mode has null bridge adapter ──────────────────────────────
    assert isinstance(
        svc._bridge, OfflineBridgeAdapter
    ), f"Expected OfflineBridgeAdapter in Recipe A; got {type(svc._bridge).__name__!r}"
    assert (
        svc._bridge.get_client() is None
    ), "OfflineBridgeAdapter.get_client() must return None — no outbox in offline mode"

    await svc.shutdown()
