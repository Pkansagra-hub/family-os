import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import pytest

from k1.bridge_k0.command_client import Command, CommandReceipt, CommandStatus
from k1.bridge_k0.wal_writer import (
    WALLogEntry,
    WALLogType,
    WALTopic,
    WALWriter,
    WALWriterConfig,
)


class FakeCommandClient:
    def __init__(self) -> None:
        self.sent_commands: List[Dict[str, Any]] = []

    async def send_command(self, command: Command, cognitive_trace_id: Optional[str] = None) -> CommandReceipt:
        payload = json.loads(command.payload.decode("utf-8"))
        self.sent_commands.append(
            {
                "command": command,
                "trace": cognitive_trace_id,
                "payload": payload,
            }
        )
        return CommandReceipt(
            receipt_id=f"rcpt_{command.command_id}",
            command_id=command.command_id,
            status=CommandStatus.SUCCESS,
            timestamp_ms=int(time.time() * 1000),
            signature="sig",
        )


@pytest.mark.asyncio
async def test_log_batches_by_count_and_flushes_immediately():
    client = FakeCommandClient()
    config = WALWriterConfig(batch_size_max=2, batch_size_bytes=10_000)
    writer = WALWriter(config, command_client=client)
    await writer.initialize()

    entry1 = WALLogEntry(
        log_id="log1",
        topic=WALTopic.SAGA_LOG,
        log_type=WALLogType.SAGA_START,
        saga_id="saga",
        timestamp=1,
        payload={"foo": "bar"},
        cognitive_trace_id="trace1",
    )
    entry2 = WALLogEntry(
        log_id="log2",
        topic=WALTopic.SAGA_LOG,
        log_type=WALLogType.STEP_COMPLETE,
        saga_id="saga",
        timestamp=2,
        payload={"foo": "baz"},
        cognitive_trace_id="trace2",
    )

    await writer.log(entry1)
    result = await writer.log(entry2)

    assert result.batched is False
    assert len(client.sent_commands) == 1
    batch_payload = client.sent_commands[0]["payload"]
    assert batch_payload["count"] == 2
    assert {e["log_id"] for e in batch_payload["entries"]} == {"log1", "log2"}

    await writer.shutdown()


@pytest.mark.asyncio
async def test_log_batches_by_size_trigger():
    client = FakeCommandClient()
    config = WALWriterConfig(batch_size_max=100, batch_size_bytes=200)
    writer = WALWriter(config, command_client=client)
    await writer.initialize()

    payload = {"blob": "x" * 400}
    entry = WALLogEntry(
        log_id="big",
        topic=WALTopic.SAGA_LOG,
        log_type=WALLogType.SAGA_START,
        saga_id="saga",
        timestamp=1,
        payload=payload,
    )

    result = await writer.log(entry)
    assert result.batched is False
    assert len(client.sent_commands) == 1

    await writer.shutdown()


@pytest.mark.asyncio
async def test_timer_flushes_after_interval():
    client = FakeCommandClient()
    config = WALWriterConfig(batch_size_max=10, batch_size_bytes=10_000, batch_flush_interval_ms=50)
    writer = WALWriter(config, command_client=client)
    await writer.initialize()

    entry = WALLogEntry(
        log_id="timer",
        topic=WALTopic.SAGA_LOG,
        log_type=WALLogType.SAGA_START,
        saga_id="saga",
        timestamp=1,
        payload={"a": 1},
    )

    await writer.log(entry)
    await asyncio.sleep(0.1)

    assert len(client.sent_commands) == 1
    await writer.shutdown()


@pytest.mark.asyncio
async def test_shutdown_flushes_pending_entries():
    client = FakeCommandClient()
    config = WALWriterConfig(batch_size_max=10, batch_size_bytes=10_000)
    writer = WALWriter(config, command_client=client)
    await writer.initialize()

    entry = WALLogEntry(
        log_id="late",
        topic=WALTopic.SAGA_LOG,
        log_type=WALLogType.SAGA_START,
        saga_id="saga",
        timestamp=1,
        payload={"a": 1},
    )

    await writer.log(entry)
    assert len(client.sent_commands) == 0

    await writer.shutdown()
    assert len(client.sent_commands) == 1


@pytest.mark.asyncio
async def test_queue_capacity_exceeded_raises():
    client = FakeCommandClient()
    config = WALWriterConfig(batch_size_max=100, batch_size_bytes=10_000)
    writer = WALWriter(config, command_client=client)
    await writer.initialize()

    entry = WALLogEntry(
        log_id="cap",
        topic=WALTopic.SAGA_LOG,
        log_type=WALLogType.SAGA_START,
        saga_id="saga",
        timestamp=1,
        payload={"a": 1},
    )

    writer.config.queue_capacity = 0
    with pytest.raises(RuntimeError):
        await writer.log(entry)

    await writer.shutdown()
