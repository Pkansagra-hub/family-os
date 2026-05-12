"""Tests for SQLiteWorkflowAdapter (Issue 4.1.5).

These are integration-style tests against a real SQLite file.

Covers:
  - DB init + WAL mode + schema_version
  - Workflow CRUD roundtrip
  - Trigger persistence + due trigger selection
  - Run persistence (stored as JSON)
  - Gap persistence + pending gap retrieval
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.state_read_port import IStateReadPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import (
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    TriggerSpec,
    TriggerType,
)
from k1.orchestrator.workflows.persistence.sqlite_adapter import SQLiteWorkflowAdapter
from k1.orchestrator.workflows.system_clock import FrozenClock
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_types import WorkflowSpec


def _step(step_id: str = "s1", cap: str = "cap.test") -> PlanStep:
    return PlanStep(id=step_id, capability=cap, params={"k": "v"})


def _spec(
    workflow_id: str = "wf-1",
    name: str = "WF",
    version: str = "1.0.0",
    active: bool = True,
    created_at: float = 1000.0,
    updated_at: float = 1000.0,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id="plan-1",
        version=version,
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[_step()],
        dependencies={},
        active=active,
        created_at=created_at,
        updated_at=updated_at,
        created_by="system",
    )


class TestSQLiteInit:
    @pytest.mark.asyncio
    async def test_creates_schema_and_wal(self, tmp_path) -> None:
        db_path = tmp_path / "workflows.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        adapter.close()

        conn = sqlite3.connect(str(db_path))
        try:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert str(journal_mode).lower() == "wal"

            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "schema_version" in tables
            assert "workflows" in tables
            assert "triggers" in tables
            assert "runs" in tables
            assert "gaps" in tables

            version = conn.execute("SELECT schema_version FROM schema_version").fetchone()[0]
            assert int(version) == 1
        finally:
            conn.close()


class TestProtocolConformance:
    @pytest.mark.asyncio
    async def test_adapter_is_instance_of_port_protocol(self, tmp_path) -> None:
        db_path = tmp_path / "proto.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            assert isinstance(adapter, IWorkflowStoragePort)
        finally:
            adapter.close()


class TestWorkflowCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get_roundtrip(self, tmp_path) -> None:
        db_path = tmp_path / "wf.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-001", name="Test")
            await adapter.save_workflow(spec)
            loaded = await adapter.get_workflow("wf-001")
            assert loaded == spec
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_list_active_only(self, tmp_path) -> None:
        db_path = tmp_path / "wf2.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            a = _spec(workflow_id="a", name="A", active=True)
            b = _spec(workflow_id="b", name="B", active=False)
            await adapter.save_workflow(a)
            await adapter.save_workflow(b)

            active = await adapter.list_workflows(active_only=True)
            assert [w.workflow_id for w in active] == ["a"]

            all_wf = await adapter.list_workflows(active_only=False)
            assert {w.workflow_id for w in all_wf} == {"a", "b"}
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_soft_delete_sets_active_false(self, tmp_path) -> None:
        db_path = tmp_path / "wf3.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1", active=True)
            await adapter.save_workflow(spec)
            await adapter.delete_workflow("wf-1")
            loaded = await adapter.get_workflow("wf-1")
            assert loaded is not None
            assert loaded.active is False
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_purge_removes_workflow(self, tmp_path) -> None:
        db_path = tmp_path / "wf4.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)
            await adapter.purge_workflow("wf-1")
            assert await adapter.get_workflow("wf-1") is None
        finally:
            adapter.close()


class TestTriggerState:
    @pytest.mark.asyncio
    async def test_save_cron_trigger_is_due_initially(self, tmp_path) -> None:
        db_path = tmp_path / "trg.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)

            trig = TriggerSpec(
                type=TriggerType.CRON,
                schedule="0 9 * * MON",
                timezone="UTC",
                enabled=True,
            )
            await adapter.save_trigger("wf-1", trig)

            due = await adapter.get_due_triggers(now=1.0)
            assert due == [("wf-1", trig)]
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_manual_trigger_not_due(self, tmp_path) -> None:
        db_path = tmp_path / "trg2.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)

            trig = TriggerSpec(type=TriggerType.MANUAL)
            await adapter.save_trigger("wf-1", trig)

            due = await adapter.get_due_triggers(now=time.time())
            assert due == []
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_disabled_cron_trigger_not_due(self, tmp_path) -> None:
        db_path = tmp_path / "trg3.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)

            trig = TriggerSpec(
                type=TriggerType.CRON,
                schedule="0 9 * * MON",
                enabled=False,
            )
            await adapter.save_trigger("wf-1", trig)

            due = await adapter.get_due_triggers(now=1.0)
            assert due == []
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_update_trigger_state_changes_due(self, tmp_path) -> None:
        db_path = tmp_path / "trg4.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)

            trig = TriggerSpec(type=TriggerType.CRON, schedule="0 9 * * MON")
            await adapter.save_trigger("wf-1", trig)

            await adapter.update_trigger_state("wf-1", next_fire=5000.0, last_fire=100.0)
            due = await adapter.get_due_triggers(now=200.0)
            assert due == []

            due2 = await adapter.get_due_triggers(now=5000.0)
            # M5.2: deserialized TriggerSpec now reflects the persisted
            # last_fire timestamp via the last_triggered_at field.
            expected = TriggerSpec(
                type=TriggerType.CRON,
                schedule="0 9 * * MON",
                last_triggered_at=100.0,
            )
            assert due2 == [("wf-1", expected)]
        finally:
            adapter.close()


class TestGaps:
    @pytest.mark.asyncio
    async def test_save_gap_and_get_pending(self, tmp_path) -> None:
        db_path = tmp_path / "gaps.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)

            gap = ProactiveGap(
                workflow_id="wf-1",
                gap_type="CAPABILITY_REMOVED",
                affected_step_id="s1",
                capability_name="cap.missing",
                old_contract_version="1",
                new_contract_version="N/A",
                description="missing",
                justification="cannot run",
                status=ProactiveGapStatus.PENDING,
            )
            await adapter.save_gap(gap)

            pending = await adapter.get_pending_gaps()
            assert len(pending) == 1
            assert pending[0].workflow_id == "wf-1"
            assert pending[0].gap_type == "CAPABILITY_REMOVED"
            assert pending[0].status == ProactiveGapStatus.PENDING
        finally:
            adapter.close()


class TestRuns:
    @pytest.mark.asyncio
    async def test_save_run_and_get_runs(self, tmp_path) -> None:
        db_path = tmp_path / "runs.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            spec = _spec(workflow_id="wf-1")
            await adapter.save_workflow(spec)

            class DummyRun:
                def __init__(self) -> None:
                    self.run_id = "run-1"
                    self.workflow_id = "wf-1"
                    self.version = "1.0.0"
                    self.compiled_hash = "abc"
                    self.trigger_type = "CRON"
                    self.status = "RUNNING"
                    self.started_at = 123.0
                    self.completed_at = None

            await adapter.save_run(DummyRun())
            runs = await adapter.get_runs("wf-1", limit=10)
            assert len(runs) == 1
            assert runs[0]["run_id"] == "run-1"
            assert runs[0]["workflow_id"] == "wf-1"
        finally:
            adapter.close()


class TestEpic41Wiring:
    """End-to-end wiring smoke: SQLite adapter + registry + compiler."""

    class _FakeFabric(IFabricGatewayPort):
        async def execute(self, request: object) -> object:  # pragma: no cover
            raise NotImplementedError

        async def execute_batch(self, requests: list) -> list:  # pragma: no cover
            raise NotImplementedError

        async def query_registry(self, capability_name: str):
            # Always missing -> forces CAPABILITY_REMOVED gap.
            return None

    class _FakeDelta(IDeltaEmitPort):
        def __init__(self) -> None:
            self.events = []

        async def emit(self, event_topic: str, payload: dict, trace_id: str) -> None:
            self.events.append((event_topic, payload, trace_id))

        async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
            return None

    class _FakeState(IStateReadPort):
        async def read_section(self, session_id: str, section: str):
            return None

        async def read_sections(self, session_id: str, names: list):
            return {}

        async def get_snapshot(self, session_id: str):
            return None

    @pytest.mark.asyncio
    async def test_registry_uses_sqlite_adapter(self, tmp_path) -> None:
        db_path = tmp_path / "wiring.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            registry = WorkflowRegistry(adapter)
            spec = _spec(workflow_id="wf-epic", name="Epic")
            await registry.save(spec)
            loaded = await registry.get("wf-epic")
            assert loaded is not None
            assert loaded.workflow_id == "wf-epic"

            # Trigger update persists trigger in adapter.
            await registry.update_trigger(
                "wf-epic",
                TriggerSpec(type=TriggerType.CRON, schedule="0 9 * * MON"),
            )
            due = await adapter.get_due_triggers(now=1.0)
            assert due and due[0][0] == "wf-epic"
        finally:
            adapter.close()

    @pytest.mark.asyncio
    async def test_compiler_persists_gap_via_sqlite_adapter(self, tmp_path) -> None:
        db_path = tmp_path / "wiring2.db"
        adapter = SQLiteWorkflowAdapter(str(db_path))
        try:
            registry = WorkflowRegistry(adapter)
            spec = _spec(workflow_id="wf-gap", name="GapWF")
            await registry.save(spec)

            compiler = WorkflowCompiler(
                fabric=self._FakeFabric(),
                delta=self._FakeDelta(),
                storage=adapter,
                state_port=self._FakeState(),
                clock=FrozenClock(1700000000.0),
            )

            result = await compiler.compile(spec)
            assert result.success is False

            pending = await adapter.get_pending_gaps()
            assert len(pending) == 1
            assert pending[0].workflow_id == "wf-gap"
            assert pending[0].status == ProactiveGapStatus.PENDING
        finally:
            adapter.close()
