import asyncio
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import pytest

import k1.bridge_k0.state_delta_emitter as emitter_module
from k1.bridge_k0.batch_client import FlushTrigger, SessionStateDelta
from k1.bridge_k0.command_client import CommandStatus
from k1.bridge_k0.state_delta_emitter import (
    DeltaEmitResult,
    DeltaOperation,
    SessionSection,
    StateDelta,
    StateDeltaEmitter,
    StateDeltaEmitterConfig,
)


@dataclass
class FakeBatchReceipt:
    status: CommandStatus
    receipt_id: str = "rcpt"


class FakeBatchClient:
    def __init__(self, *, auto_receipt: bool = False) -> None:
        self.auto_receipt = auto_receipt
        self.added: List[Tuple[SessionStateDelta, Optional[str]]] = []
        self.flush_calls: List[Tuple[FlushTrigger, Optional[str]]] = []

    async def add_delta(self, delta: SessionStateDelta, cognitive_trace_id: Optional[str] = None):
        self.added.append((delta, cognitive_trace_id))
        if self.auto_receipt:
            return FakeBatchReceipt(CommandStatus.SUCCESS)
        return None

    async def flush(self, trigger: FlushTrigger, cognitive_trace_id: Optional[str] = None):
        self.flush_calls.append((trigger, cognitive_trace_id))
        return FakeBatchReceipt(CommandStatus.SUCCESS)


def make_state_delta(label: str, *, privacy: str = "GREEN") -> StateDelta:
    return StateDelta(
        session_id="sess",
        section=SessionSection.META,
        field_path="beliefs.user",
        operation=DeltaOperation.SET,
        value={"value": label},
        timestamp=int(time.time() * 1000),
        cognitive_trace_id="trace",
        privacy_band=privacy,
    )


@pytest.mark.asyncio
async def test_emit_deltas_triggers_flush_on_size_threshold():
    fake_batch = FakeBatchClient(auto_receipt=True)
    emitter = StateDeltaEmitter(
        StateDeltaEmitterConfig(batch_size_max_bytes=16, batch_count_max=10),
        batch_client=fake_batch,
    )

    result = await emitter.emit_deltas([make_state_delta("delta")])

    assert isinstance(result, DeltaEmitResult)
    assert not result.batched
    assert len(fake_batch.added) == 1


@pytest.mark.asyncio
async def test_emit_deltas_skips_black_privacy():
    fake_batch = FakeBatchClient(auto_receipt=True)
    emitter = StateDeltaEmitter(
        StateDeltaEmitterConfig(batch_size_max_bytes=16, batch_count_max=10),
        batch_client=fake_batch,
    )

    result = await emitter.emit_deltas([make_state_delta("secret", privacy="BLACK")])

    assert result.batched
    assert fake_batch.added == []


@pytest.mark.asyncio
async def test_shutdown_flushes_pending_batch_and_cancels_timer():
    fake_batch = FakeBatchClient()
    emitter = StateDeltaEmitter(
        StateDeltaEmitterConfig(batch_flush_interval_ms=50, batch_size_max_bytes=1024),
        batch_client=fake_batch,
    )
    await emitter.initialize()

    # Add delta without triggering immediate flush
    await emitter.emit_deltas([make_state_delta("pending")])
    await emitter.shutdown()

    assert fake_batch.flush_calls  # manual flush executed


@pytest.mark.asyncio
async def test_compute_deltas_converts_deepdiff(monkeypatch):
    fake_batch = FakeBatchClient()
    emitter = StateDeltaEmitter(StateDeltaEmitterConfig(), batch_client=fake_batch)

    diff_payload = {
        "values_changed": {
            "root['beliefs']['user']": {
                "old_value": "old",
                "new_value": "new",
            }
        }
    }

    def fake_deepdiff(old, new, max_level, verbose_level):  # noqa: ARG001
        return diff_payload

    monkeypatch.setattr(emitter_module, "DeepDiff", fake_deepdiff)

    class SessionState:
        def __init__(self, session_id: str, value: str) -> None:
            self.session_id = session_id
            self._value = value
            self.cognitive_trace_id = "trace"
            self.privacy_band = "GREEN"

        def to_dict(self) -> dict[str, Any]:
            return {"beliefs": {"user": self._value}}

    old_state = SessionState("sess", "old")
    new_state = SessionState("sess", "new")

    deltas = await emitter.compute_deltas(old_state, new_state)

    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.operation == DeltaOperation.SET
    assert "beliefs" in delta.field_path
    assert delta.value == "new"


@pytest.mark.asyncio
async def test_flush_loop_triggers_time_based_flush():
    fake_batch = FakeBatchClient(auto_receipt=True)
    emitter = StateDeltaEmitter(
        StateDeltaEmitterConfig(batch_flush_interval_ms=30, batch_size_max_bytes=1024),
        batch_client=fake_batch,
    )
    await emitter.initialize()

    await emitter.emit_deltas([make_state_delta("delta")])
    await asyncio.sleep(0.05)
    await emitter.shutdown()

    # Add delta should have been flushed by timer
    assert fake_batch.added
