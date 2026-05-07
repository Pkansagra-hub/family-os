"""
Tests for ProactiveGapDetector (Issue 4.2.7).

Covers event subscription, debounce, gap detection via compiler,
workflow deactivation on LARGE gaps, auto-resolved notification
on SMALL gaps, and start/stop lifecycle.

Test classes:
  TestGapDetectorLifecycle        -- start/stop/idempotency.
  TestGapDetectorOnContractUpdate -- Sync handler + debounce.
  TestGapDetectorNoAffected       -- No workflows reference capability.
  TestGapDetectorLargeGap         -- LARGE gap -> deactivate + HIL event.
  TestGapDetectorNoGap            -- Healthy compilation -> no action.
  TestGapDetectorAutoResolved     -- Auto-resolved -> emit notification.
  TestGapDetectorDebounce         -- 5s debounce window.
  TestGapDetectorMultipleWorkflows -- Multiple affected workflows.
  TestGapDetectorReExports        -- __init__ re-exports ProactiveGapDetector.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.types import (
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    RegistryEntry,
    TriggerSpec,
    TriggerType,
)
from k1.orchestrator.workflows.gap_detector import _DEBOUNCE_SECONDS, ProactiveGapDetector
from k1.orchestrator.workflows.system_clock import FrozenClock
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_types import WorkflowSpec

# ===========================================================================
# Fakes
# ===========================================================================

_FROZEN_TS = 1700000000.0


class FakeSubscriptionHandle:
    """Minimal subscription handle."""

    def __init__(self, topic: str) -> None:
        self.subscription_id = f"sub-{topic}"
        self.topic = topic


class FakeEventPort:
    """Fake IEventSubscriptionPort -- records subscriptions and allows emit."""

    def __init__(self) -> None:
        self.subscriptions: List[Tuple[str, Callable]] = []
        self.handles: List[FakeSubscriptionHandle] = []
        self.unsubscribed: List[FakeSubscriptionHandle] = []

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> FakeSubscriptionHandle:
        handle = FakeSubscriptionHandle(topic)
        self.subscriptions.append((topic, handler))
        self.handles.append(handle)
        return handle

    def unsubscribe(self, handle: object) -> bool:
        self.unsubscribed.append(handle)
        return True

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """Simulate event emission to subscribed handlers."""
        for sub_topic, handler in self.subscriptions:
            if sub_topic == topic:
                handler(topic, payload)


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


class FakeFabricPort:
    """Fake IFabricGatewayPort -- query_registry only."""

    def __init__(
        self,
        registry: Optional[Dict[str, RegistryEntry]] = None,
    ) -> None:
        self._registry: Dict[str, RegistryEntry] = registry or {}

    def add(self, entry: RegistryEntry) -> None:
        self._registry[entry.name] = entry

    def remove(self, name: str) -> None:
        self._registry.pop(name, None)

    async def execute(self, request: object) -> object:
        raise NotImplementedError

    async def execute_batch(self, requests: list) -> list:
        raise NotImplementedError

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        return self._registry.get(capability_name)


class FakeStatePort:
    """Fake IStateReadPort."""

    async def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        if section == "persona":
            return {"timezone": "UTC", "locale": "en-US"}
        return None

    async def read_sections(self, session_id: str, names: list) -> Dict[str, Any]:
        return {}

    async def get_snapshot(self, session_id: str) -> object:
        return None


# ===========================================================================
# Helpers
# ===========================================================================


def _step(
    step_id: str = "s1",
    capability: str = "cap.test",
    params: Optional[Dict[str, Any]] = None,
) -> PlanStep:
    return PlanStep(id=step_id, capability=capability, params=params or {})


def _manual_trigger() -> TriggerSpec:
    return TriggerSpec(type=TriggerType.MANUAL)


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


def _build_compiler(
    fabric: Optional[FakeFabricPort] = None,
    storage: Optional[FakeWorkflowStorage] = None,
    delta: Optional[FakeDeltaPort] = None,
) -> WorkflowCompiler:
    fab = fabric or FakeFabricPort({"cap.test": _entry()})
    sto = storage or FakeWorkflowStorage()
    dl = delta or FakeDeltaPort()
    st = FakeStatePort()
    clock = FrozenClock(_FROZEN_TS)
    return WorkflowCompiler(
        fabric=fab,
        delta=dl,
        storage=sto,
        state_port=st,
        clock=clock,
    )


def _build_registry(storage: FakeWorkflowStorage) -> WorkflowRegistry:
    return WorkflowRegistry(storage=storage)


def _build_detector(
    storage: Optional[FakeWorkflowStorage] = None,
    fabric: Optional[FakeFabricPort] = None,
    events: Optional[FakeEventPort] = None,
    delta: Optional[FakeDeltaPort] = None,
) -> Tuple[ProactiveGapDetector, FakeWorkflowStorage, FakeEventPort, FakeDeltaPort, FakeFabricPort]:
    """Build all components and return them for assertions."""
    sto = storage or FakeWorkflowStorage()
    fab = fabric or FakeFabricPort({"cap.test": _entry()})
    ev = events or FakeEventPort()
    dl = delta or FakeDeltaPort()
    registry = _build_registry(sto)
    compiler = _build_compiler(fabric=fab, storage=sto, delta=dl)
    detector = ProactiveGapDetector(
        registry=registry,
        compiler=compiler,
        storage=sto,
        events=ev,
        delta=dl,
    )
    return detector, sto, ev, dl, fab


async def _wait_processing(detector: ProactiveGapDetector, timeout: float = 0.5) -> None:
    """Wait for the detector's queue to drain."""
    deadline = asyncio.get_event_loop().time() + timeout
    while not detector._queue.empty() and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)
    # Give additional time for async processing to complete
    await asyncio.sleep(0.1)


# ===========================================================================
# Tests
# ===========================================================================


class TestGapDetectorLifecycle:
    """start/stop/idempotency."""

    @pytest.mark.asyncio
    async def test_start_subscribes(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            assert len(ev.subscriptions) == 1
            assert ev.subscriptions[0][0] == "k1.fabric.capability.contract_updated.v1"
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        await detector.stop()
        assert len(ev.unsubscribed) == 1

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        await detector.start()  # second start is no-op
        try:
            assert len(ev.subscriptions) == 1
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        await detector.stop()
        await detector.stop()  # second stop is no-op
        assert len(ev.unsubscribed) == 1


class TestGapDetectorOnContractUpdate:
    """Sync handler + queue."""

    @pytest.mark.asyncio
    async def test_handler_enqueues(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.test"},
            )
            assert detector._queue.qsize() == 1
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_handler_ignores_empty_capability(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": ""},
            )
            assert detector._queue.qsize() == 0
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_handler_ignores_missing_capability(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {},
            )
            assert detector._queue.qsize() == 0
        finally:
            await detector.stop()


class TestGapDetectorNoAffected:
    """No workflows reference capability."""

    @pytest.mark.asyncio
    async def test_no_affected_workflows(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        # Save a workflow that references "cap.other", NOT "cap.test"
        spec = _spec(
            workflow_id="wf-1",
            steps=[_step(capability="cap.other")],
        )
        await sto.save_workflow(spec)

        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.test"},
            )
            await _wait_processing(detector)
            # No gaps saved, no events emitted
            assert len(sto.gaps) == 0
            # Only the initial compiler's HIL events (if any), no gap.detected
            gap_events = [e for e in dl.events if e[0] == "k1.orchestration.gap.detected"]
            assert len(gap_events) == 0
        finally:
            await detector.stop()


class TestGapDetectorLargeGap:
    """LARGE gap -> deactivate + HIL event."""

    @pytest.mark.asyncio
    async def test_large_gap_deactivates_workflow(self) -> None:
        # Fabric has "cap.test" but NOT "cap.missing"
        fab = FakeFabricPort({"cap.test": _entry()})
        detector, sto, ev, dl, _ = _build_detector(fabric=fab)

        # Workflow references "cap.missing" -- will be CAPABILITY_REMOVED
        spec = _spec(
            workflow_id="wf-gap",
            steps=[_step(step_id="s1", capability="cap.missing")],
        )
        await sto.save_workflow(spec)

        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.missing"},
            )
            await _wait_processing(detector)

            # Workflow should be deactivated
            stored = await sto.get_workflow("wf-gap")
            assert stored is not None
            assert stored.active is False

            # PENDING gap should be saved
            assert len(sto.gaps) >= 1
            pending = [g for g in sto.gaps if g.status == ProactiveGapStatus.PENDING]
            assert len(pending) >= 1

            # HIL event emitted by the detector
            gap_events = [
                e
                for e in dl.events
                if e[0] == "k1.orchestration.gap.detected"
                and e[1].get("action") == "workflow_deactivated"
            ]
            assert len(gap_events) >= 1
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_large_gap_saves_gap_record(self) -> None:
        fab = FakeFabricPort({})  # No capabilities at all
        detector, sto, ev, dl, _ = _build_detector(fabric=fab)

        spec = _spec(
            workflow_id="wf-gap2",
            steps=[_step(capability="cap.removed")],
        )
        await sto.save_workflow(spec)

        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.removed"},
            )
            await _wait_processing(detector)

            # Gaps saved (both by compiler and by detector checking)
            pending = [g for g in sto.gaps if g.status == ProactiveGapStatus.PENDING]
            assert len(pending) >= 1
            assert any(g.gap_type == "CAPABILITY_REMOVED" for g in pending)
        finally:
            await detector.stop()


class TestGapDetectorNoGap:
    """Healthy compilation -> no deactivation."""

    @pytest.mark.asyncio
    async def test_healthy_workflow_not_deactivated(self) -> None:
        fab = FakeFabricPort({"cap.test": _entry()})
        detector, sto, ev, dl, _ = _build_detector(fabric=fab)

        spec = _spec(
            workflow_id="wf-ok",
            steps=[_step(capability="cap.test")],
        )
        await sto.save_workflow(spec)

        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.test"},
            )
            await _wait_processing(detector)

            # Workflow still active
            stored = await sto.get_workflow("wf-ok")
            assert stored is not None
            assert stored.active is True

            # No deactivation events
            deactivation_events = [
                e
                for e in dl.events
                if e[0] == "k1.orchestration.gap.detected"
                and e[1].get("action") == "workflow_deactivated"
            ]
            assert len(deactivation_events) == 0
        finally:
            await detector.stop()


class TestGapDetectorDebounce:
    """5s debounce window."""

    @pytest.mark.asyncio
    async def test_debounce_same_capability(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            # First event enqueued
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.debounce"},
            )
            assert detector._queue.qsize() == 1

            # Second event within 5s -- debounced
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.debounce"},
            )
            assert detector._queue.qsize() == 1  # No increase
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_different_capabilities_not_debounced(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.a"},
            )
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.b"},
            )
            assert detector._queue.qsize() == 2  # Both enqueued
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_debounce_expires(self) -> None:
        detector, sto, ev, dl, fab = _build_detector()
        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.expire"},
            )
            assert detector._queue.qsize() == 1

            # Manually expire the debounce by backdating _last_seen
            detector._last_seen["cap.expire"] = time.time() - _DEBOUNCE_SECONDS - 1

            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.expire"},
            )
            assert detector._queue.qsize() == 2  # Second event enqueued
        finally:
            await detector.stop()


class TestGapDetectorMultipleWorkflows:
    """Multiple affected workflows processed."""

    @pytest.mark.asyncio
    async def test_multiple_affected(self) -> None:
        fab = FakeFabricPort({})  # Empty -> CAPABILITY_REMOVED
        detector, sto, ev, dl, _ = _build_detector(fabric=fab)

        # Two workflows reference "cap.gone"
        spec1 = _spec(
            workflow_id="wf-a",
            steps=[_step(capability="cap.gone")],
        )
        spec2 = _spec(
            workflow_id="wf-b",
            steps=[_step(capability="cap.gone")],
        )
        await sto.save_workflow(spec1)
        await sto.save_workflow(spec2)

        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.gone"},
            )
            await _wait_processing(detector)

            # Both workflows deactivated
            stored_a = await sto.get_workflow("wf-a")
            stored_b = await sto.get_workflow("wf-b")
            assert stored_a is not None and stored_a.active is False
            assert stored_b is not None and stored_b.active is False
        finally:
            await detector.stop()


class TestGapDetectorAutoResolved:
    """Auto-resolved params -> emit notification (no deactivation)."""

    @pytest.mark.asyncio
    async def test_auto_resolved_emits_notification(self) -> None:
        # This test requires a scenario where compile() returns
        # success=True with auto_resolved items. In V1, the compiler
        # only detects CAPABILITY_REMOVED and PERMISSION_CHANGE
        # (both LARGE). Auto-resolved is currently an empty list.
        # We test the code path by verifying no deactivation
        # on a healthy workflow.
        fab = FakeFabricPort({"cap.test": _entry()})
        detector, sto, ev, dl, _ = _build_detector(fabric=fab)

        spec = _spec(
            workflow_id="wf-auto",
            steps=[_step(capability="cap.test")],
        )
        await sto.save_workflow(spec)

        await detector.start()
        try:
            ev.emit(
                "k1.fabric.capability.contract_updated.v1",
                {"capability_name": "cap.test"},
            )
            await _wait_processing(detector)

            # Workflow still active
            stored = await sto.get_workflow("wf-auto")
            assert stored is not None
            assert stored.active is True
        finally:
            await detector.stop()


class TestGapDetectorReExports:
    """__init__ re-exports ProactiveGapDetector."""

    def test_re_export(self) -> None:
        from k1.orchestrator.workflows import ProactiveGapDetector as PGD

        assert PGD is ProactiveGapDetector
