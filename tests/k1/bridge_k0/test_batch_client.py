import asyncio
import time
from typing import List, Optional, Tuple

import pytest

from k1.bridge_k0.batch_client import BatchClient, FlushTrigger, SessionStateDelta
from k1.bridge_k0.command_client import CommandReceipt, CommandStatus, Priority


class FakeCommandClient:
    """Minimal CommandClient stub respecting ADR-0022 receipt semantics."""

    def __init__(
        self,
        *,
        fail: bool = False,
        pending: bool = False,
    ) -> None:
        self.fail = fail
        self.pending = pending
        self.commands: List[Tuple] = []

    async def send_command(self, command, cognitive_trace_id: Optional[str] = None) -> CommandReceipt:
        self.commands.append((command, cognitive_trace_id))
        if self.fail:
            raise RuntimeError("send failed")

        status = CommandStatus.PENDING if self.pending else CommandStatus.SUCCESS
        return CommandReceipt(
            receipt_id=f"rcpt_{len(self.commands)}",
            command_id=command.command_id,
            status=status,
            timestamp_ms=int(time.time() * 1000),
            signature="sig",
        )


def make_delta(
    session_id: str,
    label: str,
    *,
    priority: Priority = Priority.REALTIME,
    size_bytes: int = 0,
) -> SessionStateDelta:
    return SessionStateDelta(
        session_id=session_id,
        field_path="beliefs.user",
        value={"value": label},
        timestamp=time.time() * 1000,
        priority=priority.value,
        size_bytes=size_bytes,
    )


@pytest.mark.asyncio
async def test_count_trigger_flushes_batch():
    client = FakeCommandClient()
    batch = BatchClient(
        config={"batch_count_max": 2, "batch_window_ms": 1000},
        command_client=client,
    )
    await batch.initialize()

    assert await batch.add_delta(make_delta("sess", "delta-1")) is None
    receipt = await batch.add_delta(make_delta("sess", "delta-2"))

    assert receipt is not None
    assert len(client.commands) == 1

    await batch.shutdown()


@pytest.mark.asyncio
async def test_size_trigger_flushes_batch_immediately():
    client = FakeCommandClient()
    batch = BatchClient(
        config={"batch_size_bytes": 32, "batch_window_ms": 1000},
        command_client=client,
    )
    await batch.initialize()

    receipt = await batch.add_delta(make_delta("sess", "delta", size_bytes=64))
    assert receipt is not None
    assert len(client.commands) == 1

    await batch.shutdown()


@pytest.mark.asyncio
async def test_timer_trigger_flushes_after_window():
    client = FakeCommandClient()
    batch = BatchClient(
        config={"batch_window_ms": 20, "batch_size_bytes": 1024},
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "delta"))
    await asyncio.sleep(0.05)

    assert len(client.commands) == 1

    await batch.shutdown()


@pytest.mark.asyncio
async def test_manual_flush_returns_receipt():
    client = FakeCommandClient()
    batch = BatchClient(
        config={"batch_window_ms": 1000, "batch_size_bytes": 1024},
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "delta"))
    receipt = await batch.flush(FlushTrigger.MANUAL)

    assert receipt is not None
    assert len(client.commands) == 1

    await batch.shutdown()


@pytest.mark.asyncio
async def test_background_deltas_dropped_when_buffer_full():
    client = FakeCommandClient()
    batch = BatchClient(
        config={
            "batch_window_ms": 1000,
            "batch_size_bytes": 2048,
            "max_buffer_bytes": 60,
        },
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "first", priority=Priority.BACKGROUND, size_bytes=40))
    await batch.add_delta(make_delta("sess", "second", priority=Priority.BACKGROUND, size_bytes=40))

    assert len(batch._batch_buffer) == 1  # noqa: SLF001
    assert batch._batch_buffer[0][0].value["value"] == "second"  # noqa: SLF001

    await batch.shutdown()


@pytest.mark.asyncio
async def test_error_when_no_background_delta_to_drop():
    client = FakeCommandClient()
    batch = BatchClient(
        config={
            "batch_window_ms": 1000,
            "batch_size_bytes": 1024,
            "max_buffer_bytes": 10,
        },
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "critical", priority=Priority.CRITICAL, size_bytes=8))

    with pytest.raises(RuntimeError):
        await batch.add_delta(make_delta("sess", "critical-2", priority=Priority.CRITICAL, size_bytes=8))

    await batch.shutdown()


@pytest.mark.asyncio
async def test_pending_receipt_limit_enforced():
    client = FakeCommandClient(pending=True)
    batch = BatchClient(
        config={
            "batch_window_ms": 1000,
            "batch_size_bytes": 16,
            "pending_receipts_max": 1,
            "enable_batching": False,
        },
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "delta", size_bytes=32))

    with pytest.raises(RuntimeError):
        await batch.add_delta(make_delta("sess", "delta-2", size_bytes=32))

    await batch.shutdown()


@pytest.mark.asyncio
async def test_failed_flush_goes_to_dlq():
    client = FakeCommandClient(fail=True)
    batch = BatchClient(
        config={
            "batch_window_ms": 1000,
            "batch_size_bytes": 65536,
            "enable_batching": True,
        },
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "delta"))

    with pytest.raises(RuntimeError):
        await batch.flush(FlushTrigger.MANUAL)

    assert len(batch.dlq) == 1

    # Simulate transport recovery so shutdown can drain without raising.
    client.fail = False
    await batch.shutdown()


@pytest.mark.asyncio
async def test_shutdown_flushes_outstanding_batch():
    client = FakeCommandClient()
    batch = BatchClient(
        config={"batch_window_ms": 10, "batch_size_bytes": 1024},
        command_client=client,
    )
    await batch.initialize()

    await batch.add_delta(make_delta("sess", "delta"))
    await batch.shutdown()

    assert batch.state == "TERMINATED"
    assert len(client.commands) >= 1
