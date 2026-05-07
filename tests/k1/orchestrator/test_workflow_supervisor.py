"""
Tests for RunManifest (4.2.4), WorkflowRunSupervisor (4.2.3),
CrossWorkflowResolver + WorkflowDepthGuard (4.2.5 + 4.2.6).

Test classes:
  -- RunManifest (4.2.4) --
  TestRunStatusEnum               -- Enum values and membership.
  TestRunManifestCreate            -- Factory method: run_id, started_at, RUNNING.
  TestRunManifestTransitions       -- complete/fail/abort produce new instances.
  TestRunManifestTerminalGuard     -- Cannot transition from terminal status.
  TestRunManifestFrozen            -- Immutability of frozen dataclass.

  -- WorkflowRunSupervisor (4.2.3) --
  TestSupervisorStartRun           -- Happy path start with compilation.
  TestSupervisorStartRunNotFound   -- WorkflowNotFoundError for missing workflow.
  TestSupervisorStartRunInactive   -- WorkflowNotFoundError for inactive workflow.
  TestSupervisorStartRunCompileFail -- Compilation failure returns FAILED manifest.
  TestSupervisorConcurrentRunAbort -- Single-active-run policy: abort predecessor.
  TestSupervisorCompleteRun        -- complete_run transitions + emits event.
  TestSupervisorFailRun            -- fail_run transitions + emits event.
  TestSupervisorDeliverResult      -- Session-aware result delivery (PROD-4).

  -- WorkflowDepthGuard (4.2.6) --
  TestDepthGuardCheck              -- Depth enforcement.
  TestDepthGuardCycleDetection     -- Cycle detection.
  TestDepthGuardInit               -- Constructor validation.

  -- CrossWorkflowResolver (4.2.5) --
  TestResolverIsWorkflowStep       -- Pattern matching for workflow.run.*.
  TestResolverExtractWorkflowId    -- Extract workflow_id from capability.
  TestResolverResolveSuccess       -- Full resolve happy path.
  TestResolverResolveNotWorkflow   -- Non-workflow capability returns None.
  TestResolverResolveNotFound      -- Missing workflow returns None.
  TestResolverResolveInactive      -- Inactive workflow returns None.
  TestResolverResolveDepthExceeded -- MaxDepthError raised.
  TestResolverResolveCycleDetected -- WorkflowCycleError raised.
  TestResolverCompileFail          -- Compilation failure returns None.

  -- Re-exports --
  TestWorkflowInitExports          -- __init__.py re-exports new symbols.
"""

from __future__ import annotations

import time
from dataclasses import FrozenInstanceError
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.types import (
    AggregatedResult,
    CommittedPlan,
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    RegistryEntry,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.cross_workflow_resolver import (
    CrossWorkflowResolver,
    MaxDepthError,
    WorkflowCycleError,
    WorkflowDepthGuard,
)
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_supervisor import (
    StartRunResult,
    WorkflowNotFoundError,
    WorkflowRunSupervisor,
)
from k1.orchestrator.workflows.workflow_types import RunManifest, RunStatus, WorkflowSpec

# ===========================================================================
# Fakes
# ===========================================================================

_FROZEN_TS = 1700000000.0


class FakeDeltaPort:
    """Fake IDeltaEmitPort -- records emitted events."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any], str]] = []
        self.progress: List[Tuple[str, str, str]] = []
        self.hil_requests: list = []

    async def emit(
        self,
        event_topic: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        self.events.append((event_topic, payload, trace_id))

    async def emit_progress(
        self,
        step_id: str,
        summary: str,
        trace_id: str,
    ) -> None:
        self.progress.append((step_id, summary, trace_id))

class FakeBridgePort:
    """Fake IBridgeWritePort -- records deferred results."""

    def __init__(self) -> None:
        self.deferred: List[Tuple[Any, str, str]] = []
        self.audits: list = []
        self.wals: list = []

    async def submit_audit(self, run_manifest: object, trace_id: str) -> None:
        self.audits.append((run_manifest, trace_id))

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Any,
        trace_id: str,
    ) -> None:
        self.wals.append((dag_id, entry_type, payload, trace_id))

    async def read_wal(self, dag_id: str) -> list:
        return []

    async def list_wal_ids(self) -> list:
        return []

    async def submit_deferred_result(
        self,
        result: Any,
        workflow_id: str,
        trace_id: str,
    ) -> None:
        self.deferred.append((result, workflow_id, trace_id))


class FakeWorkflowStorage:
    """Fake IWorkflowStoragePort -- dict-based in-memory."""

    def __init__(self) -> None:
        self.workflows: Dict[str, WorkflowSpec] = {}
        self.gaps: List[ProactiveGap] = []
        self.runs: list = []

    async def save_workflow(self, spec: WorkflowSpec) -> None:
        self.workflows[spec.workflow_id] = spec

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]:
        return self.workflows.get(workflow_id)

    async def list_workflows(self, active_only: bool = True) -> List[WorkflowSpec]:
        specs = list(self.workflows.values())
        if active_only:
            return [s for s in specs if s.active]
        return specs

    async def delete_workflow(self, workflow_id: str) -> None:
        pass

    async def purge_workflow(self, workflow_id: str) -> None:
        pass

    async def save_trigger(self, workflow_id: str, trigger: object) -> None:
        pass

    async def get_due_triggers(self, now: float) -> List[Tuple[str, object]]:
        return []

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        pass

    async def save_run(self, manifest: object) -> None:
        self.runs.append(manifest)

    async def get_runs(self, workflow_id: str, limit: int = 10) -> list:
        return [r for r in self.runs if getattr(r, "workflow_id", None) == workflow_id][:limit]

    async def save_gap(self, gap: ProactiveGap) -> None:
        self.gaps.append(gap)

    async def get_pending_gaps(self) -> List[ProactiveGap]:
        return [g for g in self.gaps if g.status == ProactiveGapStatus.PENDING]


class FakeFabricPort:
    """Fake IFabricGatewayPort -- query_registry only."""

    def __init__(
        self,
        registry: Optional[Dict[str, RegistryEntry]] = None,
    ) -> None:
        self._registry: Dict[str, RegistryEntry] = registry or {}

    def add(self, entry: RegistryEntry) -> None:
        self._registry[entry.name] = entry

    async def execute(self, request: object) -> object:
        raise NotImplementedError

    async def execute_batch(self, requests: list) -> list:
        raise NotImplementedError

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        return self._registry.get(capability_name)


class FakeStatePort:
    """Fake IStateReadPort -- returns configured user prefs."""

    def __init__(
        self,
        prefs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._prefs = prefs or {"timezone": "UTC", "locale": "en-US"}

    async def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        if section == "persona":
            return dict(self._prefs)
        return None

    async def read_sections(self, session_id: str, names: list) -> Dict[str, Any]:
        return {}

    async def get_snapshot(self, session_id: str) -> object:
        return None


# ===========================================================================
# Helpers
# ===========================================================================


def _step(
    step_id: str = "s1", capability: str = "cap.test", params: Optional[Dict[str, Any]] = None
) -> PlanStep:
    return PlanStep(id=step_id, capability=capability, params=params or {})


def _manual_trigger() -> TriggerSpec:
    return TriggerSpec(type=TriggerType.MANUAL)


def _spec(
    workflow_id: str = "wf-001",
    name: str = "Test WF",
    version: str = "1.0.0",
    trigger: TriggerSpec | None = None,
    steps: list[PlanStep] | None = None,
    active: bool = True,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id="plan-001",
        version=version,
        trigger=trigger or _manual_trigger(),
        steps=[_step()] if steps is None else steps,
        dependencies={},
        active=active,
    )


def _entry(
    name: str = "cap.test",
    safety_band_min: str = "low",
) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="tool",
        safety_band_min=safety_band_min,
        availability="available",
    )


def _workflow_run_request(
    workflow_id: str = "wf-001",
    version: str = "1.0.0",
    trigger_type: TriggerType = TriggerType.MANUAL,
    trace_id: str = "trace-001",
) -> WorkflowRunRequest:
    return WorkflowRunRequest(
        workflow_id=workflow_id,
        version=version,
        trigger_type=trigger_type,
        trace_id=trace_id,
    )


def _aggregated_result(
    success: bool = True,
    trace_id: str = "trace-001",
) -> AggregatedResult:
    return AggregatedResult(
        total_steps=1,
        completed=1 if success else 0,
        failed=0 if success else 1,
        cancelled=0,
        skipped=0,
        step_results=[],
        success=success,
        duration_ms=150,
        trace_id=trace_id,
    )


from k1.orchestrator.workflows.system_clock import FrozenClock


def _build_compiler(
    fabric: Optional[FakeFabricPort] = None,
    state: Optional[FakeStatePort] = None,
    storage: Optional[FakeWorkflowStorage] = None,
    delta: Optional[FakeDeltaPort] = None,
) -> WorkflowCompiler:
    """Build a WorkflowCompiler with sensible fake deps."""
    fab = fabric or FakeFabricPort({"cap.test": _entry()})
    st = state or FakeStatePort()
    sto = storage or FakeWorkflowStorage()
    dl = delta or FakeDeltaPort()
    clock = FrozenClock(_FROZEN_TS)
    return WorkflowCompiler(
        fabric=fab,
        delta=dl,
        storage=sto,
        state_port=st,
        clock=clock,
    )


def _build_registry(storage: Optional[FakeWorkflowStorage] = None) -> WorkflowRegistry:
    """Build a WorkflowRegistry with a fake storage."""
    return WorkflowRegistry(storage=storage or FakeWorkflowStorage())


# ===========================================================================
# RunManifest (4.2.4)
# ===========================================================================


class TestRunStatusEnum:
    """Enum values and membership."""

    def test_four_members(self) -> None:
        assert len(RunStatus) == 4

    def test_running_value(self) -> None:
        assert RunStatus.RUNNING.value == "RUNNING"

    def test_completed_value(self) -> None:
        assert RunStatus.COMPLETED.value == "COMPLETED"

    def test_failed_value(self) -> None:
        assert RunStatus.FAILED.value == "FAILED"

    def test_aborted_value(self) -> None:
        assert RunStatus.ABORTED.value == "ABORTED"

    def test_from_string(self) -> None:
        assert RunStatus("RUNNING") is RunStatus.RUNNING
        assert RunStatus("COMPLETED") is RunStatus.COMPLETED


class TestRunManifestCreate:
    """Factory method: run_id, started_at, RUNNING."""

    def test_create_sets_running(self) -> None:
        m = RunManifest.create(
            workflow_id="wf-1",
            version="1.0.0",
            compiled_hash="abc",
            trigger_type="MANUAL",
            total_steps=3,
        )
        assert m.status == RunStatus.RUNNING

    def test_create_generates_run_id(self) -> None:
        m = RunManifest.create(
            workflow_id="wf-1",
            version="1.0.0",
            compiled_hash="abc",
            trigger_type="MANUAL",
            total_steps=3,
        )
        assert m.run_id  # non-empty
        assert len(m.run_id) == 36  # UUID format

    def test_create_sets_started_at(self) -> None:
        before = time.time()
        m = RunManifest.create(
            workflow_id="wf-1",
            version="1.0.0",
            compiled_hash="abc",
            trigger_type="MANUAL",
            total_steps=3,
        )
        after = time.time()
        assert before <= m.started_at <= after

    def test_create_fields(self) -> None:
        m = RunManifest.create(
            workflow_id="wf-1",
            version="2.0.0",
            compiled_hash="xyz",
            trigger_type="CRON",
            total_steps=5,
        )
        assert m.workflow_id == "wf-1"
        assert m.version == "2.0.0"
        assert m.compiled_hash == "xyz"
        assert m.trigger_type == "CRON"
        assert m.steps_total == 5
        assert m.steps_completed == 0
        assert m.completed_at is None
        assert m.result_summary is None
        assert m.error_message is None

    def test_create_unique_ids(self) -> None:
        m1 = RunManifest.create("wf-1", "1.0.0", "h", "MANUAL", 1)
        m2 = RunManifest.create("wf-1", "1.0.0", "h", "MANUAL", 1)
        assert m1.run_id != m2.run_id


class TestRunManifestTransitions:
    """complete/fail/abort produce new frozen instances."""

    def _make(self) -> RunManifest:
        return RunManifest.create("wf-1", "1.0.0", "h", "MANUAL", 3)

    def test_complete_returns_new_instance(self) -> None:
        m = self._make()
        c = m.complete(result_summary={"ok": True})
        assert c is not m
        assert c.status == RunStatus.COMPLETED
        assert c.result_summary == {"ok": True}
        assert c.completed_at is not None
        assert c.steps_completed == c.steps_total

    def test_complete_without_summary(self) -> None:
        m = self._make()
        c = m.complete()
        assert c.status == RunStatus.COMPLETED
        assert c.result_summary is None

    def test_fail_returns_new_instance(self) -> None:
        m = self._make()
        f = m.fail("something broke")
        assert f is not m
        assert f.status == RunStatus.FAILED
        assert f.error_message == "something broke"
        assert f.completed_at is not None

    def test_abort_returns_new_instance(self) -> None:
        m = self._make()
        a = m.abort()
        assert a is not m
        assert a.status == RunStatus.ABORTED
        assert a.completed_at is not None

    def test_original_unchanged_after_transition(self) -> None:
        m = self._make()
        m.complete()
        assert m.status == RunStatus.RUNNING  # Original not mutated


class TestRunManifestTerminalGuard:
    """Cannot transition from terminal status."""

    def _make(self) -> RunManifest:
        return RunManifest.create("wf-1", "1.0.0", "h", "MANUAL", 3)

    def test_completed_cannot_complete(self) -> None:
        c = self._make().complete()
        with pytest.raises(ValueError, match="terminal"):
            c.complete()

    def test_completed_cannot_fail(self) -> None:
        c = self._make().complete()
        with pytest.raises(ValueError, match="terminal"):
            c.fail("err")

    def test_completed_cannot_abort(self) -> None:
        c = self._make().complete()
        with pytest.raises(ValueError, match="terminal"):
            c.abort()

    def test_failed_cannot_complete(self) -> None:
        f = self._make().fail("err")
        with pytest.raises(ValueError, match="terminal"):
            f.complete()

    def test_aborted_cannot_complete(self) -> None:
        a = self._make().abort()
        with pytest.raises(ValueError, match="terminal"):
            a.complete()

    def test_aborted_cannot_fail(self) -> None:
        a = self._make().abort()
        with pytest.raises(ValueError, match="terminal"):
            a.fail("err")


class TestRunManifestFrozen:
    """Immutability of frozen dataclass."""

    def test_cannot_set_status(self) -> None:
        m = RunManifest.create("wf-1", "1.0.0", "h", "MANUAL", 3)
        with pytest.raises(FrozenInstanceError):
            m.status = RunStatus.COMPLETED  # type: ignore[misc]

    def test_cannot_set_run_id(self) -> None:
        m = RunManifest.create("wf-1", "1.0.0", "h", "MANUAL", 3)
        with pytest.raises(FrozenInstanceError):
            m.run_id = "hacked"  # type: ignore[misc]


# ===========================================================================
# WorkflowRunSupervisor (4.2.3)
# ===========================================================================


class TestSupervisorStartRun:
    """Happy path start with compilation."""

    @pytest.fixture
    def storage(self) -> FakeWorkflowStorage:
        s = FakeWorkflowStorage()
        return s

    @pytest.fixture
    def delta(self) -> FakeDeltaPort:
        return FakeDeltaPort()

    @pytest.fixture
    def bridge(self) -> FakeBridgePort:
        return FakeBridgePort()

    @pytest.fixture
    def fabric(self) -> FakeFabricPort:
        return FakeFabricPort({"cap.test": _entry()})

    @pytest.fixture
    def compiler(
        self, fabric: FakeFabricPort, storage: FakeWorkflowStorage, delta: FakeDeltaPort
    ) -> WorkflowCompiler:
        return _build_compiler(fabric=fabric, storage=storage, delta=delta)

    @pytest.fixture
    def registry(self, storage: FakeWorkflowStorage) -> WorkflowRegistry:
        return _build_registry(storage)

    @pytest.fixture
    def supervisor(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        storage: FakeWorkflowStorage,
        delta: FakeDeltaPort,
        bridge: FakeBridgePort,
    ) -> WorkflowRunSupervisor:
        return WorkflowRunSupervisor(
            registry=registry,
            compiler=compiler,
            storage=storage,
            delta=delta,
            bridge=bridge,
        )

    @pytest.mark.asyncio
    async def test_start_run_success(
        self, supervisor: WorkflowRunSupervisor, storage: FakeWorkflowStorage
    ) -> None:
        spec = _spec(workflow_id="wf-001")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-001")
        result = await supervisor.start_run(req)

        assert isinstance(result, StartRunResult)
        assert result.manifest.status == RunStatus.RUNNING
        assert result.manifest.workflow_id == "wf-001"
        assert result.compiled_plan is not None

    @pytest.mark.asyncio
    async def test_start_run_persists_manifest(
        self, supervisor: WorkflowRunSupervisor, storage: FakeWorkflowStorage
    ) -> None:
        spec = _spec(workflow_id="wf-001")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-001")
        result = await supervisor.start_run(req)

        # At least one run saved (the RUNNING manifest)
        run_manifests = [r for r in storage.runs if getattr(r, "workflow_id", None) == "wf-001"]
        assert len(run_manifests) >= 1
        assert run_manifests[-1].status == RunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_run_emits_event(
        self,
        supervisor: WorkflowRunSupervisor,
        storage: FakeWorkflowStorage,
        delta: FakeDeltaPort,
    ) -> None:
        spec = _spec(workflow_id="wf-001")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-001")
        await supervisor.start_run(req)

        topics = [e[0] for e in delta.events]
        assert "k1.orchestration.workflow.run_started" in topics


class TestSupervisorStartRunNotFound:
    """WorkflowNotFoundError for missing workflow."""

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        req = _workflow_run_request(workflow_id="missing")
        with pytest.raises(WorkflowNotFoundError) as exc:
            await sup.start_run(req)
        assert exc.value.workflow_id == "missing"


class TestSupervisorStartRunInactive:
    """WorkflowNotFoundError for inactive workflow."""

    @pytest.mark.asyncio
    async def test_inactive_raises(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-dead", active=False)
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-dead")
        with pytest.raises(WorkflowNotFoundError):
            await sup.start_run(req)


class TestSupervisorStartRunCompileFail:
    """Compilation failure returns FAILED manifest."""

    @pytest.mark.asyncio
    async def test_compile_fail_returns_failed_manifest(self) -> None:
        storage = FakeWorkflowStorage()
        # Fabric with NO capabilities -- compilation will fail
        fabric = FakeFabricPort({})
        registry = _build_registry(storage)
        compiler = _build_compiler(fabric=fabric, storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-fail")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-fail")
        result = await sup.start_run(req)

        assert result.manifest.status == RunStatus.FAILED
        assert result.compiled_plan is None
        assert "Compilation failed" in (result.manifest.error_message or "")


class TestSupervisorConcurrentRunAbort:
    """Single-active-run policy: abort predecessor."""

    @pytest.mark.asyncio
    async def test_aborts_running_predecessor(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-conc")
        await storage.save_workflow(spec)

        # First run
        req1 = _workflow_run_request(workflow_id="wf-conc", trace_id="t1")
        r1 = await sup.start_run(req1)
        assert r1.manifest.status == RunStatus.RUNNING

        # Second run -- should abort first
        req2 = _workflow_run_request(workflow_id="wf-conc", trace_id="t2")
        r2 = await sup.start_run(req2)
        assert r2.manifest.status == RunStatus.RUNNING
        assert r2.manifest.run_id != r1.manifest.run_id

        # Check abort event was emitted
        abort_events = [e for e in delta.events if e[0] == "k1.orchestration.workflow.run_aborted"]
        assert len(abort_events) >= 1


class TestSupervisorCompleteRun:
    """complete_run transitions + emits event."""

    @pytest.mark.asyncio
    async def test_complete_run_transitions(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-comp")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-comp")
        started = await sup.start_run(req)
        result = _aggregated_result()

        completed = await sup.complete_run(started.manifest, result)
        assert completed.status == RunStatus.COMPLETED
        assert completed.result_summary is not None

    @pytest.mark.asyncio
    async def test_complete_run_emits_event(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-comp2")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-comp2")
        started = await sup.start_run(req)
        result = _aggregated_result()
        await sup.complete_run(started.manifest, result)

        topics = [e[0] for e in delta.events]
        assert "k1.orchestration.workflow.run_completed" in topics


class TestSupervisorFailRun:
    """fail_run transitions + emits event."""

    @pytest.mark.asyncio
    async def test_fail_run_transitions(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-fl")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-fl")
        started = await sup.start_run(req)

        failed = await sup.fail_run(started.manifest, "boom", "trace-x")
        assert failed.status == RunStatus.FAILED
        assert failed.error_message == "boom"

    @pytest.mark.asyncio
    async def test_fail_run_emits_event(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-fl2")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-fl2")
        started = await sup.start_run(req)
        await sup.fail_run(started.manifest, "boom", "trace-x")

        topics = [e[0] for e in delta.events]
        assert "k1.orchestration.workflow.run_failed" in topics


class TestSupervisorDeliverResult:
    """Session-aware result delivery (PROD-4)."""

    @pytest.mark.asyncio
    async def test_deliver_session_active(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-d")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-d")
        started = await sup.start_run(req)
        result = _aggregated_result()
        completed = await sup.complete_run(started.manifest, result)

        await sup.deliver_result(completed, result, session_active=True)

        # Should emit via delta (not bridge)
        result_events = [e for e in delta.events if e[0] == "k1.orchestration.workflow.result"]
        assert len(result_events) == 1
        assert len(bridge.deferred) == 0

    @pytest.mark.asyncio
    async def test_deliver_session_inactive(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        delta = FakeDeltaPort()
        bridge = FakeBridgePort()
        sup = WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)

        spec = _spec(workflow_id="wf-d2")
        await storage.save_workflow(spec)

        req = _workflow_run_request(workflow_id="wf-d2")
        started = await sup.start_run(req)
        result = _aggregated_result()
        completed = await sup.complete_run(started.manifest, result)

        await sup.deliver_result(completed, result, session_active=False)

        # Should use bridge (not delta result event)
        assert len(bridge.deferred) == 1
        result_events = [e for e in delta.events if e[0] == "k1.orchestration.workflow.result"]
        assert len(result_events) == 0


# ===========================================================================
# WorkflowDepthGuard (4.2.6)
# ===========================================================================


class TestDepthGuardCheck:
    """Depth enforcement."""

    def test_within_depth(self) -> None:
        guard = WorkflowDepthGuard(max_depth=3)
        guard.check(1)
        guard.check(2)
        guard.check(3)  # Should not raise

    def test_exceeds_depth(self) -> None:
        guard = WorkflowDepthGuard(max_depth=3)
        with pytest.raises(MaxDepthError) as exc:
            guard.check(4)
        assert exc.value.current_depth == 4
        assert exc.value.max_depth == 3

    def test_exact_boundary(self) -> None:
        guard = WorkflowDepthGuard(max_depth=2)
        guard.check(2)  # OK
        with pytest.raises(MaxDepthError):
            guard.check(3)  # Exceeds

    def test_default_max_depth(self) -> None:
        guard = WorkflowDepthGuard()
        assert guard.max_depth == 3


class TestDepthGuardCycleDetection:
    """Cycle detection."""

    def test_no_cycle(self) -> None:
        guard = WorkflowDepthGuard()
        guard.detect_cycle("wf-c", {"wf-a", "wf-b"})  # Should not raise

    def test_cycle_detected(self) -> None:
        guard = WorkflowDepthGuard()
        with pytest.raises(WorkflowCycleError) as exc:
            guard.detect_cycle("wf-a", {"wf-a", "wf-b"})
        assert exc.value.workflow_id == "wf-a"

    def test_empty_ancestors(self) -> None:
        guard = WorkflowDepthGuard()
        guard.detect_cycle("wf-x", set())  # Should not raise


class TestDepthGuardInit:
    """Constructor validation."""

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="max_depth must be >= 1"):
            WorkflowDepthGuard(max_depth=0)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="max_depth must be >= 1"):
            WorkflowDepthGuard(max_depth=-1)

    def test_accepts_one(self) -> None:
        guard = WorkflowDepthGuard(max_depth=1)
        assert guard.max_depth == 1


# ===========================================================================
# CrossWorkflowResolver (4.2.5)
# ===========================================================================


class TestResolverIsWorkflowStep:
    """Pattern matching for workflow.run.*."""

    def test_matches_workflow_run(self) -> None:
        step = _step(capability="workflow.run.my-wf")
        assert CrossWorkflowResolver.is_workflow_step(step) is True

    def test_no_match_regular_cap(self) -> None:
        step = _step(capability="cap.test")
        assert CrossWorkflowResolver.is_workflow_step(step) is False

    def test_no_match_partial(self) -> None:
        step = _step(capability="workflow.run")
        assert CrossWorkflowResolver.is_workflow_step(step) is False

    def test_matches_dotted_id(self) -> None:
        step = _step(capability="workflow.run.my.nested.wf")
        assert CrossWorkflowResolver.is_workflow_step(step) is True


class TestResolverExtractWorkflowId:
    """Extract workflow_id from capability."""

    def test_extract_simple(self) -> None:
        assert CrossWorkflowResolver.extract_workflow_id("workflow.run.abc") == "abc"

    def test_extract_dotted(self) -> None:
        assert CrossWorkflowResolver.extract_workflow_id("workflow.run.a.b.c") == "a.b.c"

    def test_non_match(self) -> None:
        assert CrossWorkflowResolver.extract_workflow_id("cap.test") is None


class TestResolverResolveSuccess:
    """Full resolve happy path."""

    @pytest.mark.asyncio
    async def test_resolve_returns_committed_plan(self) -> None:
        storage = FakeWorkflowStorage()
        sub_spec = _spec(workflow_id="sub-wf", name="Sub WF")
        await storage.save_workflow(sub_spec)

        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        guard = WorkflowDepthGuard(max_depth=3)
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(step_id="s-sub", capability="workflow.run.sub-wf")
        result = await resolver.resolve(step, {}, current_depth=1)

        assert result is not None
        assert isinstance(result, CommittedPlan)


class TestResolverResolveNotWorkflow:
    """Non-workflow capability returns None."""

    @pytest.mark.asyncio
    async def test_non_workflow_returns_none(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        guard = WorkflowDepthGuard()
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(capability="cap.regular")
        result = await resolver.resolve(step, {}, current_depth=1)
        assert result is None


class TestResolverResolveNotFound:
    """Missing workflow returns None."""

    @pytest.mark.asyncio
    async def test_missing_workflow_returns_none(self) -> None:
        storage = FakeWorkflowStorage()
        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        guard = WorkflowDepthGuard()
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(capability="workflow.run.nonexistent")
        result = await resolver.resolve(step, {}, current_depth=1)
        assert result is None


class TestResolverResolveInactive:
    """Inactive workflow returns None."""

    @pytest.mark.asyncio
    async def test_inactive_workflow_returns_none(self) -> None:
        storage = FakeWorkflowStorage()
        sub_spec = _spec(workflow_id="dead-wf", active=False)
        await storage.save_workflow(sub_spec)

        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        guard = WorkflowDepthGuard()
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(capability="workflow.run.dead-wf")
        result = await resolver.resolve(step, {}, current_depth=1)
        assert result is None


class TestResolverResolveDepthExceeded:
    """MaxDepthError raised when depth limit exceeded."""

    @pytest.mark.asyncio
    async def test_depth_exceeded(self) -> None:
        storage = FakeWorkflowStorage()
        sub_spec = _spec(workflow_id="deep-wf")
        await storage.save_workflow(sub_spec)

        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        guard = WorkflowDepthGuard(max_depth=2)
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(capability="workflow.run.deep-wf")
        with pytest.raises(MaxDepthError):
            await resolver.resolve(step, {}, current_depth=2)


class TestResolverResolveCycleDetected:
    """WorkflowCycleError raised when cycle detected."""

    @pytest.mark.asyncio
    async def test_cycle_detected(self) -> None:
        storage = FakeWorkflowStorage()
        sub_spec = _spec(workflow_id="cycle-wf")
        await storage.save_workflow(sub_spec)

        registry = _build_registry(storage)
        compiler = _build_compiler(storage=storage)
        guard = WorkflowDepthGuard()
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(capability="workflow.run.cycle-wf")
        with pytest.raises(WorkflowCycleError) as exc:
            await resolver.resolve(
                step, {}, current_depth=1, ancestor_ids={"cycle-wf", "parent-wf"}
            )
        assert exc.value.workflow_id == "cycle-wf"


class TestResolverCompileFail:
    """Compilation failure returns None."""

    @pytest.mark.asyncio
    async def test_compile_fail_returns_none(self) -> None:
        storage = FakeWorkflowStorage()
        # Sub-workflow with a capability not in registry
        sub_spec = _spec(
            workflow_id="bad-wf",
            steps=[_step(capability="missing.cap")],
        )
        await storage.save_workflow(sub_spec)

        # Fabric has no capabilities -- compilation will fail
        fabric = FakeFabricPort({})
        registry = _build_registry(storage)
        compiler = _build_compiler(fabric=fabric, storage=storage)
        guard = WorkflowDepthGuard()
        resolver = CrossWorkflowResolver(registry, compiler, guard)

        step = _step(capability="workflow.run.bad-wf")
        result = await resolver.resolve(step, {}, current_depth=1)
        assert result is None


# ===========================================================================
# Re-exports
# ===========================================================================


class TestWorkflowInitExports:
    """__init__.py re-exports new symbols."""

    def test_cross_workflow_resolver_export(self) -> None:
        from k1.orchestrator.workflows import CrossWorkflowResolver as CWR  # noqa: F811

        assert CWR is CrossWorkflowResolver

    def test_depth_guard_export(self) -> None:
        from k1.orchestrator.workflows import WorkflowDepthGuard as WDG  # noqa: F811

        assert WDG is WorkflowDepthGuard

    def test_max_depth_error_export(self) -> None:
        from k1.orchestrator.workflows import MaxDepthError as MDE  # noqa: F811

        assert MDE is MaxDepthError

    def test_cycle_error_export(self) -> None:
        from k1.orchestrator.workflows import WorkflowCycleError as WCE  # noqa: F811

        assert WCE is WorkflowCycleError

    def test_supervisor_export(self) -> None:
        from k1.orchestrator.workflows import WorkflowRunSupervisor as WRS  # noqa: F811

        assert WRS is WorkflowRunSupervisor

    def test_start_run_result_export(self) -> None:
        from k1.orchestrator.workflows import StartRunResult as SRR  # noqa: F811

        assert SRR is StartRunResult

    def test_not_found_error_export(self) -> None:
        from k1.orchestrator.workflows import WorkflowNotFoundError as WNF  # noqa: F811

        assert WNF is WorkflowNotFoundError

    def test_run_manifest_export(self) -> None:
        from k1.orchestrator.workflows import RunManifest as RM  # noqa: F811

        assert RM is RunManifest

    def test_run_status_export(self) -> None:
        from k1.orchestrator.workflows import RunStatus as RS  # noqa: F811

        assert RS is RunStatus
