from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.phase_interface import P03RunnerContext
from k0.runtime.sequential_adapter import SequentialRunnerAdapter


class _RecordingRunner:
    def __init__(self) -> None:
        self.envelopes: list[object] = []

    async def run(self, envelope, runner_ctx):
        self.envelopes.append(envelope)
        return SimpleNamespace(success=True)


class _FakeConnection:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *params):
        self.calls.append((query, params))
        return self.rows


class _FakeUnitOfWork:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._connection = _FakeConnection(rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSyscalls:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._uow = _FakeUnitOfWork(rows)

    def unit_of_work(self):
        return self._uow


def _make_adapter() -> SequentialRunnerAdapter:
    spec = MagicMock()
    spec.pipeline_id = "P03_CONSOLIDATION"
    adapter = SequentialRunnerAdapter(spec=spec, runner_class=MagicMock, registry=MagicMock())
    adapter._runner = _RecordingRunner()
    return adapter


@pytest.mark.asyncio
async def test_execute_cycle_uses_explicit_trigger_scope() -> None:
    adapter = _make_adapter()
    syscalls = _FakeSyscalls(
        [{"tenant_id": "tenant-a", "space_id": "space-a"}],
    )
    runner_ctx = P03RunnerContext.create(
        syscalls=syscalls,
        logger=logging.getLogger("test.sequential_adapter.explicit"),
        config={
            "trigger_context": {
                "reason": "Manual test",
                "options": {
                    "tenant_id": "tenant-test",
                    "space_id": "space-home",
                },
            }
        },
    )

    result = await adapter._execute_cycle(runner_ctx)

    assert result.success is True
    assert len(adapter._runner.envelopes) == 1
    envelope = adapter._runner.envelopes[0]
    assert envelope.context.tenant_id == "tenant-test"
    assert envelope.context.space_id == "space-home"
    assert syscalls._uow._connection.calls == []


@pytest.mark.asyncio
async def test_execute_cycle_discovers_scopes_for_unscoped_manual_trigger() -> None:
    adapter = _make_adapter()
    syscalls = _FakeSyscalls(
        [
            {"tenant_id": "tenant-one", "space_id": "space-a"},
            {"tenant_id": "tenant-two", "space_id": "space-b"},
        ],
    )
    runner_ctx = P03RunnerContext.create(
        syscalls=syscalls,
        logger=logging.getLogger("test.sequential_adapter.discovery"),
        config={
            "trigger_context": {
                "reason": "Unscoped manual test",
                "options": {},
            }
        },
    )

    result = await adapter._execute_cycle(runner_ctx)

    assert result.success is True
    assert len(adapter._runner.envelopes) == 2
    assert [
        (envelope.context.tenant_id, envelope.context.space_id)
        for envelope in adapter._runner.envelopes
    ] == [("tenant-one", "space-a"), ("tenant-two", "space-b")]
    assert len(syscalls._uow._connection.calls) == 1
    _, params = syscalls._uow._connection.calls[0]
    assert params == (None, None)
