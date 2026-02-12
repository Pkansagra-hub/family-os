"""
Tests for WorkflowCompiler (Issue 4.1.3).

Covers the 6-step compile() logic, DynamicExpr resolution,
capability validation, gap detection (SPEC-9), SHA-256 hash,
CompilationResult fields, idempotency, and SystemClock.

Test classes:
  TestSystemClock                  -- Real clock returns sane values.
  TestFrozenClock                  -- Deterministic test double.
  TestCompilationResultType        -- Dataclass fields and defaults.
  TestCompilerConstruction         -- Constructor stores 5 deps.
  TestDynamicExprResolution        -- date.today, date.now, user.*.
  TestDynamicExprOffsets           -- d/h/m/s offset arithmetic.
  TestCapabilityValidation         -- query_registry pass/fail.
  TestGapDetectionCapabilityRemoved -- LARGE gap when capability gone.
  TestGapDetectionSafetyBand       -- LARGE gap on safety_band_min change.
  TestGapNoChange                  -- No gap when registry matches.
  TestCompileSuccess               -- Full happy path: 6 steps.
  TestCompileFailsOnLargeGap       -- success=False + gap persisted + HIL.
  TestCompiledHash                 -- SHA-256 deterministic hash.
  TestIdempotency                  -- Same clock -> same result.
  TestSessionPrefs                 -- user.timezone/locale from state_port.
  TestReExports                    -- workflows __init__ exports.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from typing import Any, Dict, List, Optional, Tuple

from k1.orchestrator.types import (
    CommittedPlan,
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    RegistryEntry,
    TriggerType,
)
from k1.orchestrator.workflows.system_clock import FrozenClock, SystemClock
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_types import CompilationResult, TriggerSpec, WorkflowSpec

# ===========================================================================
# Fakes
# ===========================================================================

# Frozen timestamp: 2023-11-14 22:13:20 UTC
_FROZEN_TS = 1700000000.0
_FROZEN_DATE = "2023-11-14"


class FakeFabricPort:
    """Fake IFabricGatewayPort -- just query_registry()."""

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

    async def emit_hil_request(self, hil_request: object, trace_id: str) -> None:
        self.hil_requests.append((hil_request, trace_id))


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
        return []

    async def save_gap(self, gap: ProactiveGap) -> None:
        self.gaps.append(gap)

    async def get_pending_gaps(self) -> List[ProactiveGap]:
        return [g for g in self.gaps if g.status == ProactiveGapStatus.PENDING]


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


class FailingStatePort:
    """IStateReadPort that always raises -- tests graceful fallback."""

    async def read_section(self, session_id: str, section: str) -> None:
        raise ConnectionError("session store down")

    async def read_sections(self, session_id: str, names: list) -> Dict[str, Any]:
        raise ConnectionError("session store down")

    async def get_snapshot(self, session_id: str) -> object:
        raise ConnectionError("session store down")


# ===========================================================================
# Helpers
# ===========================================================================


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


def _step(
    step_id: str = "s1",
    capability: str = "cap.test",
    params: Optional[Dict[str, Any]] = None,
    safety_band_min: Optional[str] = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {},
        safety_band_min=safety_band_min,
    )


def _spec(
    steps: Optional[List[PlanStep]] = None,
    deps: Optional[Dict[str, List[str]]] = None,
    workflow_id: str = "wf-001",
    name: str = "Test WF",
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id="plan-001",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=steps or [_step()],
        dependencies=deps or {},
    )


def _compiler(
    fabric: Optional[FakeFabricPort] = None,
    delta: Optional[FakeDeltaPort] = None,
    storage: Optional[FakeWorkflowStorage] = None,
    state_port: Optional[FakeStatePort] = None,
    clock: Optional[FrozenClock] = None,
) -> WorkflowCompiler:
    return WorkflowCompiler(
        fabric=fabric or FakeFabricPort(),
        delta=delta or FakeDeltaPort(),
        storage=storage or FakeWorkflowStorage(),
        state_port=state_port or FakeStatePort(),
        clock=clock or FrozenClock(_FROZEN_TS),
    )


def _compiler_with_registry(
    *entries: RegistryEntry,
    delta: Optional[FakeDeltaPort] = None,
    storage: Optional[FakeWorkflowStorage] = None,
    state_port: Optional[FakeStatePort] = None,
) -> WorkflowCompiler:
    """Create compiler with pre-populated Fabric registry."""
    fabric = FakeFabricPort()
    for entry in entries:
        fabric.add(entry)
    return _compiler(
        fabric=fabric,
        delta=delta,
        storage=storage,
        state_port=state_port,
    )


# ===========================================================================
# TestSystemClock
# ===========================================================================


class TestSystemClock:
    """Real clock returns sane values."""

    def test_utc_now_is_float(self) -> None:
        clock = SystemClock()
        assert isinstance(clock.utc_now(), float)

    def test_utc_today_format(self) -> None:
        clock = SystemClock()
        today = clock.utc_today()
        # YYYY-MM-DD
        assert len(today) == 10
        assert today[4] == "-"
        assert today[7] == "-"

    def test_utc_now_datetime_has_tzinfo(self) -> None:
        clock = SystemClock()
        dt = clock.utc_now_datetime()
        assert dt.tzinfo is not None

    def test_device_local_time_utc(self) -> None:
        clock = SystemClock()
        dt = clock.device_local_time("UTC")
        assert dt.tzinfo is not None


# ===========================================================================
# TestFrozenClock
# ===========================================================================


class TestFrozenClock:
    """Deterministic test double."""

    def test_utc_now_frozen(self) -> None:
        clock = FrozenClock(_FROZEN_TS)
        assert clock.utc_now() == _FROZEN_TS

    def test_utc_today_frozen(self) -> None:
        clock = FrozenClock(_FROZEN_TS)
        assert clock.utc_today() == _FROZEN_DATE

    def test_utc_now_datetime_frozen(self) -> None:
        clock = FrozenClock(_FROZEN_TS)
        dt = clock.utc_now_datetime()
        assert dt.year == 2023
        assert dt.month == 11
        assert dt.day == 14

    def test_device_local_time_frozen(self) -> None:
        clock = FrozenClock(_FROZEN_TS)
        dt = clock.device_local_time("US/Eastern")
        assert dt.tzinfo is not None

    def test_is_subclass_of_system_clock(self) -> None:
        assert issubclass(FrozenClock, SystemClock)


# ===========================================================================
# TestCompilationResultType
# ===========================================================================


class TestCompilationResultType:
    """CompilationResult dataclass fields and defaults."""

    def test_field_count(self) -> None:
        assert len(fields(CompilationResult)) == 5

    def test_success_true_defaults(self) -> None:
        r = CompilationResult(success=True)
        assert r.compiled_plan is None
        assert r.gaps == []
        assert r.auto_resolved == []
        assert r.compiled_hash is None

    def test_all_fields(self) -> None:
        r = CompilationResult(
            success=False,
            compiled_plan=None,
            gaps=[],
            auto_resolved=["cap.a"],
            compiled_hash="abc123",
        )
        assert r.success is False
        assert r.auto_resolved == ["cap.a"]
        assert r.compiled_hash == "abc123"


# ===========================================================================
# TestCompilerConstruction
# ===========================================================================


class TestCompilerConstruction:
    """Constructor stores 5 deps."""

    def test_stores_fabric(self) -> None:
        fabric = FakeFabricPort()
        c = _compiler(fabric=fabric)
        assert c._fabric is fabric

    def test_stores_delta(self) -> None:
        delta = FakeDeltaPort()
        c = _compiler(delta=delta)
        assert c._delta is delta

    def test_stores_storage(self) -> None:
        storage = FakeWorkflowStorage()
        c = _compiler(storage=storage)
        assert c._storage is storage

    def test_stores_state_port(self) -> None:
        sp = FakeStatePort()
        c = _compiler(state_port=sp)
        assert c._state_port is sp

    def test_stores_clock(self) -> None:
        clock = FrozenClock(_FROZEN_TS)
        c = _compiler(clock=clock)
        assert c._clock is clock


# ===========================================================================
# TestDynamicExprResolution
# ===========================================================================


class TestDynamicExprResolution:
    """date.today, date.now, user.timezone, user.locale resolution."""

    async def test_date_today_resolved(self) -> None:
        step = _step(params={"d": "${date.today}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.success is True
        resolved_params = result.compiled_plan.steps[0].params
        assert resolved_params["d"] == _FROZEN_DATE

    async def test_date_now_resolved(self) -> None:
        step = _step(params={"ts": "${date.now}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["ts"] == _FROZEN_TS

    async def test_user_timezone_default(self) -> None:
        step = _step(params={"tz": "${user.timezone}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["tz"] == "UTC"

    async def test_user_locale_default(self) -> None:
        step = _step(params={"loc": "${user.locale}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["loc"] == "en-US"

    async def test_plain_params_unchanged(self) -> None:
        step = _step(params={"key": "plain value", "n": 42})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        p = result.compiled_plan.steps[0].params
        assert p["key"] == "plain value"
        assert p["n"] == 42

    async def test_mixed_params(self) -> None:
        step = _step(params={"d": "${date.today}", "s": "static"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        p = result.compiled_plan.steps[0].params
        assert p["d"] == _FROZEN_DATE
        assert p["s"] == "static"

    async def test_unknown_namespace_passthrough(self) -> None:
        step = _step(params={"x": "${custom.thing}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["x"] == "${custom.thing}"

    async def test_unknown_field_passthrough(self) -> None:
        step = _step(params={"x": "${date.unknown}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["x"] == "${date.unknown}"


# ===========================================================================
# TestDynamicExprOffsets
# ===========================================================================


class TestDynamicExprOffsets:
    """d/h/m/s offset arithmetic."""

    async def test_date_today_plus_2d(self) -> None:
        step = _step(params={"d": "${date.today +2d}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        # 2023-11-14 + 2 days = 2023-11-16
        assert result.compiled_plan.steps[0].params["d"] == "2023-11-16"

    async def test_date_today_minus_1d(self) -> None:
        step = _step(params={"d": "${date.today -1d}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        # 2023-11-14 - 1 day = 2023-11-13
        assert result.compiled_plan.steps[0].params["d"] == "2023-11-13"

    async def test_date_now_plus_1h(self) -> None:
        step = _step(params={"ts": "${date.now +1h}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["ts"] == _FROZEN_TS + 3600

    async def test_date_now_minus_30m(self) -> None:
        step = _step(params={"ts": "${date.now -30m}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["ts"] == _FROZEN_TS - 1800

    async def test_date_now_minus_120s(self) -> None:
        step = _step(params={"ts": "${date.now -120s}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.steps[0].params["ts"] == _FROZEN_TS - 120

    async def test_date_today_plus_7d(self) -> None:
        step = _step(params={"d": "${date.today +7d}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        # 2023-11-14 + 7 days = 2023-11-21
        assert result.compiled_plan.steps[0].params["d"] == "2023-11-21"


# ===========================================================================
# TestCapabilityValidation
# ===========================================================================


class TestCapabilityValidation:
    """query_registry pass/fail per step."""

    async def test_all_capabilities_found(self) -> None:
        step = _step(capability="cap.found")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry(name="cap.found"))
        result = await compiler.compile(spec)
        assert result.success is True

    async def test_missing_capability_fails(self) -> None:
        step = _step(capability="cap.gone")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry()  # empty registry
        result = await compiler.compile(spec)
        assert result.success is False
        assert len(result.gaps) == 1
        assert result.gaps[0].gap_type == "CAPABILITY_REMOVED"

    async def test_multi_step_one_missing(self) -> None:
        steps = [
            _step(step_id="s1", capability="cap.a"),
            _step(step_id="s2", capability="cap.b"),
        ]
        spec = _spec(steps=steps)
        compiler = _compiler_with_registry(_entry(name="cap.a"))
        # cap.b is missing
        result = await compiler.compile(spec)
        assert result.success is False
        assert len(result.gaps) == 1
        assert result.gaps[0].affected_step_id == "s2"

    async def test_multi_step_all_found(self) -> None:
        steps = [
            _step(step_id="s1", capability="cap.a"),
            _step(step_id="s2", capability="cap.b"),
        ]
        spec = _spec(steps=steps)
        compiler = _compiler_with_registry(_entry(name="cap.a"), _entry(name="cap.b"))
        result = await compiler.compile(spec)
        assert result.success is True
        assert len(result.gaps) == 0


# ===========================================================================
# TestGapDetectionCapabilityRemoved
# ===========================================================================


class TestGapDetectionCapabilityRemoved:
    """LARGE gap when capability is gone from registry."""

    async def test_gap_fields(self) -> None:
        step = _step(step_id="s1", capability="cap.missing")
        spec = _spec(steps=[step], workflow_id="wf-gap")
        compiler = _compiler_with_registry()
        result = await compiler.compile(spec)
        gap = result.gaps[0]
        assert gap.workflow_id == "wf-gap"
        assert gap.gap_type == "CAPABILITY_REMOVED"
        assert gap.affected_step_id == "s1"
        assert gap.capability_name == "cap.missing"
        assert gap.status == ProactiveGapStatus.PENDING

    async def test_gap_persisted(self) -> None:
        storage = FakeWorkflowStorage()
        step = _step(capability="cap.gone")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(storage=storage)
        await compiler.compile(spec)
        assert len(storage.gaps) == 1
        assert storage.gaps[0].gap_type == "CAPABILITY_REMOVED"

    async def test_hil_emitted(self) -> None:
        delta = FakeDeltaPort()
        step = _step(capability="cap.gone")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(delta=delta)
        await compiler.compile(spec)
        assert len(delta.events) == 1
        topic, payload, _ = delta.events[0]
        assert topic == "k1.orchestration.gap.detected"
        assert payload["gap_count"] == 1

    async def test_no_compiled_plan(self) -> None:
        step = _step(capability="cap.gone")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry()
        result = await compiler.compile(spec)
        assert result.compiled_plan is None
        assert result.compiled_hash is None


# ===========================================================================
# TestGapDetectionSafetyBand
# ===========================================================================


class TestGapDetectionSafetyBand:
    """LARGE gap when safety_band_min changed."""

    async def test_safety_band_change_detected(self) -> None:
        step = _step(
            capability="cap.test",
            safety_band_min="low",
        )
        entry = _entry(name="cap.test", safety_band_min="high")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(entry)
        result = await compiler.compile(spec)
        assert result.success is False
        assert len(result.gaps) == 1
        assert result.gaps[0].gap_type == "PERMISSION_CHANGE"

    async def test_safety_band_gap_fields(self) -> None:
        step = _step(
            capability="cap.test",
            safety_band_min="low",
        )
        entry = _entry(name="cap.test", safety_band_min="high")
        spec = _spec(steps=[step], workflow_id="wf-sb")
        compiler = _compiler_with_registry(entry)
        result = await compiler.compile(spec)
        gap = result.gaps[0]
        assert gap.old_contract_version == "low"
        assert gap.new_contract_version == "high"
        assert gap.workflow_id == "wf-sb"

    async def test_safety_band_none_in_step_skips(self) -> None:
        """No gap if step doesn't specify safety_band_min."""
        step = _step(capability="cap.test", safety_band_min=None)
        entry = _entry(name="cap.test", safety_band_min="high")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(entry)
        result = await compiler.compile(spec)
        assert result.success is True
        assert len(result.gaps) == 0

    async def test_safety_band_matches_no_gap(self) -> None:
        step = _step(capability="cap.test", safety_band_min="low")
        entry = _entry(name="cap.test", safety_band_min="low")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(entry)
        result = await compiler.compile(spec)
        assert result.success is True


# ===========================================================================
# TestGapNoChange
# ===========================================================================


class TestGapNoChange:
    """No gap when registry matches step expectations."""

    async def test_no_gaps_empty_result(self) -> None:
        step = _step(capability="cap.test")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.gaps == []
        assert result.auto_resolved == []


# ===========================================================================
# TestCompileSuccess
# ===========================================================================


class TestCompileSuccess:
    """Full happy path: 6 steps produce valid CommittedPlan."""

    async def test_success_flag(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.success is True

    async def test_compiled_plan_is_committed_plan(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert isinstance(result.compiled_plan, CommittedPlan)

    async def test_compiled_plan_steps_match(self) -> None:
        steps = [
            _step(step_id="s1", capability="cap.a"),
            _step(step_id="s2", capability="cap.b"),
        ]
        spec = _spec(steps=steps)
        compiler = _compiler_with_registry(_entry(name="cap.a"), _entry(name="cap.b"))
        result = await compiler.compile(spec)
        assert len(result.compiled_plan.steps) == 2
        assert result.compiled_plan.steps[0].id == "s1"
        assert result.compiled_plan.steps[1].id == "s2"

    async def test_compiled_plan_dependencies(self) -> None:
        steps = [
            _step(step_id="s1", capability="cap.a"),
            _step(step_id="s2", capability="cap.b"),
        ]
        deps = {"s2": ["s1"]}
        spec = _spec(steps=steps, deps=deps)
        compiler = _compiler_with_registry(_entry(name="cap.a"), _entry(name="cap.b"))
        result = await compiler.compile(spec)
        assert result.compiled_plan.dependencies == {"s2": ["s1"]}

    async def test_compiled_plan_plan_id(self) -> None:
        step = _step()
        spec = _spec(steps=[step], workflow_id="wf-42")
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.plan_id == "compiled-wf-42-1.0.0"

    async def test_compiled_plan_request_id(self) -> None:
        step = _step()
        spec = _spec(steps=[step], workflow_id="wf-42")
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.request_id == "wf-42"

    async def test_compiled_plan_intent(self) -> None:
        step = _step()
        spec = _spec(steps=[step], name="My Workflow")
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.intent == "Workflow: My Workflow"

    async def test_compiled_plan_created_at(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert result.compiled_plan.created_at == _FROZEN_TS

    async def test_compiled_hash_is_string(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert isinstance(result.compiled_hash, str)
        assert len(result.compiled_hash) == 64  # SHA-256 hex


# ===========================================================================
# TestCompileFailsOnLargeGap
# ===========================================================================


class TestCompileFailsOnLargeGap:
    """success=False + gap persisted + HIL emitted."""

    async def test_success_false_on_large_gap(self) -> None:
        step = _step(capability="cap.gone")
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry()
        result = await compiler.compile(spec)
        assert result.success is False

    async def test_mixed_steps_one_missing(self) -> None:
        """One good step + one missing -> fail."""
        steps = [
            _step(step_id="s1", capability="cap.ok"),
            _step(step_id="s2", capability="cap.gone"),
        ]
        spec = _spec(steps=steps)
        compiler = _compiler_with_registry(_entry(name="cap.ok"))
        result = await compiler.compile(spec)
        assert result.success is False
        assert result.compiled_plan is None

    async def test_hil_payload_structure(self) -> None:
        delta = FakeDeltaPort()
        step = _step(capability="cap.gone")
        spec = _spec(steps=[step], workflow_id="wf-hil")
        compiler = _compiler_with_registry(delta=delta)
        await compiler.compile(spec)
        _, payload, trace = delta.events[0]
        assert payload["workflow_id"] == "wf-hil"
        assert "gap_count" in payload
        assert "gap_types" in payload
        assert trace == "wf-hil"


# ===========================================================================
# TestCompiledHash
# ===========================================================================


class TestCompiledHash:
    """SHA-256 deterministic hash."""

    async def test_hash_is_sha256(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        assert len(result.compiled_hash) == 64
        # Verify it's valid hex
        int(result.compiled_hash, 16)

    async def test_same_input_same_hash(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        r1 = await compiler.compile(spec)
        r2 = await compiler.compile(spec)
        assert r1.compiled_hash == r2.compiled_hash

    async def test_different_steps_different_hash(self) -> None:
        spec_a = _spec(steps=[_step(step_id="s1", capability="cap.test")])
        spec_b = _spec(steps=[_step(step_id="s2", capability="cap.test")])
        compiler = _compiler_with_registry(_entry())
        r1 = await compiler.compile(spec_a)
        r2 = await compiler.compile(spec_b)
        assert r1.compiled_hash != r2.compiled_hash

    async def test_hash_matches_manual_computation(self) -> None:
        step = _step(params={"key": "val"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec)
        plan = result.compiled_plan
        expected_data = json.dumps(
            {
                "plan_id": plan.plan_id,
                "steps": [s.to_dict() for s in plan.steps],
                "dependencies": plan.dependencies,
            },
            sort_keys=True,
            default=str,
        )
        expected_hash = hashlib.sha256(expected_data.encode("utf-8")).hexdigest()
        assert result.compiled_hash == expected_hash


# ===========================================================================
# TestIdempotency
# ===========================================================================


class TestIdempotency:
    """Same clock time -> same result (except trace_id which is random)."""

    async def test_idempotent_resolved_params(self) -> None:
        step = _step(params={"d": "${date.today}", "ts": "${date.now}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        r1 = await compiler.compile(spec)
        r2 = await compiler.compile(spec)
        assert r1.compiled_plan.steps[0].params == (r2.compiled_plan.steps[0].params)

    async def test_idempotent_hash(self) -> None:
        step = _step(params={"d": "${date.today}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        r1 = await compiler.compile(spec)
        r2 = await compiler.compile(spec)
        assert r1.compiled_hash == r2.compiled_hash

    async def test_idempotent_success(self) -> None:
        step = _step()
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        r1 = await compiler.compile(spec)
        r2 = await compiler.compile(spec)
        assert r1.success == r2.success is True


# ===========================================================================
# TestSessionPrefs
# ===========================================================================


class TestSessionPrefs:
    """user.timezone / user.locale resolution from state_port."""

    async def test_user_timezone_from_session(self) -> None:
        state = FakeStatePort(prefs={"timezone": "America/New_York"})
        step = _step(params={"tz": "${user.timezone}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry(), state_port=state)
        result = await compiler.compile(spec, session_id="sess-1")
        assert result.compiled_plan.steps[0].params["tz"] == "America/New_York"

    async def test_user_locale_from_session(self) -> None:
        state = FakeStatePort(prefs={"locale": "fr-FR"})
        step = _step(params={"loc": "${user.locale}"})
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry(), state_port=state)
        result = await compiler.compile(spec, session_id="sess-1")
        assert result.compiled_plan.steps[0].params["loc"] == "fr-FR"

    async def test_no_session_uses_defaults(self) -> None:
        step = _step(
            params={
                "tz": "${user.timezone}",
                "loc": "${user.locale}",
            }
        )
        spec = _spec(steps=[step])
        compiler = _compiler_with_registry(_entry())
        result = await compiler.compile(spec, session_id="")
        p = result.compiled_plan.steps[0].params
        assert p["tz"] == "UTC"
        assert p["loc"] == "en-US"

    async def test_state_port_failure_uses_defaults(self) -> None:
        """Graceful fallback when state_port raises."""
        step = _step(params={"tz": "${user.timezone}"})
        spec = _spec(steps=[step])
        compiler = WorkflowCompiler(
            fabric=FakeFabricPort({"cap.test": _entry()}),
            delta=FakeDeltaPort(),
            storage=FakeWorkflowStorage(),
            state_port=FailingStatePort(),
            clock=FrozenClock(_FROZEN_TS),
        )
        result = await compiler.compile(spec, session_id="sess-1")
        assert result.compiled_plan.steps[0].params["tz"] == "UTC"


# ===========================================================================
# TestReExports
# ===========================================================================


class TestReExports:
    """workflows __init__ exports CompilationResult + WorkflowCompiler."""

    def test_compilation_result_from_init(self) -> None:
        from k1.orchestrator.workflows import CompilationResult as CR

        assert CR is CompilationResult

    def test_workflow_compiler_from_init(self) -> None:
        from k1.orchestrator.workflows import WorkflowCompiler as WC

        assert WC is WorkflowCompiler

    def test_workflow_types_all_has_9_entries(self) -> None:
        import k1.orchestrator.workflows.workflow_types as wt

        assert len(wt.__all__) == 9  # +2: RunManifest, RunStatus (4.2.4)
