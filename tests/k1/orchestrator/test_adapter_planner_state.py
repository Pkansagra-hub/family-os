"""
Tests for PlannerAdapter (6.1.3) and StateReadAdapter (6.1.4).

6.1.3 PlannerAdapter:
  TestPlannerAdapterRequestPlan   -- success, CB open, enqueue failure
  TestPlannerAdapterCancelPlan    -- success, failure (best-effort)
  TestPlannerAdapterMicroReplan   -- success, timeout, CB open, failure
  TestPlannerAdapterCBIntegration -- CB trip/reset lifecycle

6.1.4 StateReadAdapter:
  TestStateReadSection            -- success, not found, error
  TestStateReadSections           -- success, error
  TestStateReadSnapshot           -- success, error
  TestStateReadNoWriteMethods     -- ORCH-01 enforcement

  TestAdaptersReExports           -- __init__ re-exports
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.circuit_breaker.breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)
from k1.fabric.ports.state_reader import SessionSnapshot
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import (
    CommittedPlan,
    ErrorSeverity,
    MicroReplanRequest,
    PlanRequest,
    PlanStep,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_plan_request(**overrides: Any) -> PlanRequest:
    defaults: Dict[str, Any] = {
        "intent": "test-intent",
        "trace_id": "trace-001",
    }
    defaults.update(overrides)
    return PlanRequest(**defaults)


def _make_micro_replan_request(**overrides: Any) -> MicroReplanRequest:
    defaults: Dict[str, Any] = {
        "original_plan_id": "plan-001",
        "completed_results": {},
        "remaining_steps": [
            PlanStep(id="s1", capability="tool.test"),
        ],
        "trace_id": "trace-001",
    }
    defaults.update(overrides)
    return MicroReplanRequest(**defaults)


def _make_committed_plan(**overrides: Any) -> CommittedPlan:
    defaults: Dict[str, Any] = {
        "plan_id": "plan-001",
        "request_id": "req-001",
        "intent": "test",
        "steps": [
            PlanStep(id="s1", capability="tool.test"),
        ],
        "trace_id": "trace-001",
    }
    defaults.update(overrides)
    return CommittedPlan(**defaults)


def _make_cb(
    state: CircuitBreakerState = CircuitBreakerState.CLOSED,
) -> CircuitBreaker:
    """Create a CircuitBreaker in the desired state."""
    cb = CircuitBreaker(
        provider_id="planner",
        config=CircuitBreakerConfig(
            timeout_ms=45000,
            failure_threshold=2,
            failure_window_ms=60000,
            half_open_after_ms=30000,
        ),
    )
    if state == CircuitBreakerState.OPEN:
        cb.trip()
    return cb


# ===========================================================================
# Fake planner mailbox
# ===========================================================================


class FakePlannerMailbox:
    """Fake planner mailbox for testing PlannerAdapter."""

    def __init__(
        self,
        enqueue_error: Optional[Exception] = None,
        cancel_error: Optional[Exception] = None,
        micro_replan_result: Optional[CommittedPlan] = None,
        micro_replan_error: Optional[Exception] = None,
        micro_replan_delay_s: float = 0.0,
    ) -> None:
        self.enqueue_error = enqueue_error
        self.cancel_error = cancel_error
        self.micro_replan_result = micro_replan_result
        self.micro_replan_error = micro_replan_error
        self.micro_replan_delay_s = micro_replan_delay_s
        self.enqueue_calls: List[PlanRequest] = []
        self.cancel_calls: List[str] = []
        self.micro_replan_calls: List[MicroReplanRequest] = []

    async def enqueue(self, request: PlanRequest) -> None:
        self.enqueue_calls.append(request)
        if self.enqueue_error:
            raise self.enqueue_error

    async def send_cancel(self, request_id: str) -> None:
        self.cancel_calls.append(request_id)
        if self.cancel_error:
            raise self.cancel_error

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        self.micro_replan_calls.append(request)
        if self.micro_replan_delay_s > 0:
            await asyncio.sleep(self.micro_replan_delay_s)
        if self.micro_replan_error:
            raise self.micro_replan_error
        return self.micro_replan_result or _make_committed_plan()


# ===========================================================================
# Fake state reader
# ===========================================================================


class FakeStateReader:
    """Fake ISessionStateReader for testing StateReadAdapter."""

    def __init__(
        self,
        sections: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        # sections[session_id][section_name] = data
        self._sections = sections or {}
        self._error = error

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        if self._error:
            raise self._error
        return self._sections.get(session_id, {}).get(section)

    def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        if self._error:
            raise self._error
        session = self._sections.get(session_id, {})
        return {n: session[n] for n in names if n in session}

    def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        if self._error:
            raise self._error
        session = self._sections.get(session_id, {})
        return SessionSnapshot(
            session_id=session_id,
            sections=dict(session),
        )


# ===========================================================================
# 6.1.3 -- PlannerAdapter tests
# ===========================================================================


class TestPlannerAdapterRequestPlan:
    """request_plan() -- success, CB open, enqueue failure."""

    @pytest.mark.asyncio
    async def test_request_plan_success(self) -> None:
        mailbox = FakePlannerMailbox()
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        req = _make_plan_request()
        ack = await adapter.request_plan(req)

        assert ack.status == "ACCEPTED"
        assert ack.request_id == req.request_id
        assert len(mailbox.enqueue_calls) == 1

    @pytest.mark.asyncio
    async def test_request_plan_cb_open(self) -> None:
        mailbox = FakePlannerMailbox()
        cb = _make_cb(state=CircuitBreakerState.OPEN)
        adapter = PlannerAdapter(mailbox, cb)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.request_plan(_make_plan_request())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.error_code == "CB_PLANNER_OPEN"
        assert err.adapter_name == "planner"
        assert len(mailbox.enqueue_calls) == 0  # never reached mailbox

    @pytest.mark.asyncio
    async def test_request_plan_enqueue_failure(self) -> None:
        mailbox = FakePlannerMailbox(enqueue_error=RuntimeError("queue full"))
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        ack = await adapter.request_plan(_make_plan_request())
        assert ack.status == "REJECTED"
        # CB should have been tripped
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_request_plan_populates_estimated_duration(self) -> None:
        mailbox = FakePlannerMailbox()
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        req = _make_plan_request(timeout_ms=60000)
        ack = await adapter.request_plan(req)
        assert ack.estimated_duration_ms == 60000


class TestPlannerAdapterCancelPlan:
    """cancel_plan() -- success, failure (best-effort)."""

    @pytest.mark.asyncio
    async def test_cancel_success(self) -> None:
        mailbox = FakePlannerMailbox()
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        await adapter.cancel_plan("req-123")
        assert mailbox.cancel_calls == ["req-123"]

    @pytest.mark.asyncio
    async def test_cancel_failure_silent(self) -> None:
        mailbox = FakePlannerMailbox(cancel_error=RuntimeError("boom"))
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        # Should not raise -- best-effort
        await adapter.cancel_plan("req-456")
        assert mailbox.cancel_calls == ["req-456"]


class TestPlannerAdapterMicroReplan:
    """micro_replan() -- success, timeout, CB open, failure."""

    @pytest.mark.asyncio
    async def test_micro_replan_success(self) -> None:
        expected_plan = _make_committed_plan(plan_id="new-plan")
        mailbox = FakePlannerMailbox(micro_replan_result=expected_plan)
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        result = await adapter.micro_replan(_make_micro_replan_request())
        assert result is not None
        assert result.plan_id == "new-plan"
        assert len(mailbox.micro_replan_calls) == 1

    @pytest.mark.asyncio
    async def test_micro_replan_timeout_returns_none(self) -> None:
        # Delay longer than timeout (use a very short timeout for test speed)
        mailbox = FakePlannerMailbox(micro_replan_delay_s=15.0)
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        # Monkey-patch the timeout to 0.05s for test speed
        import k1.orchestrator.adapters.planner_adapter as mod

        original = mod._MICRO_REPLAN_TIMEOUT_S
        mod._MICRO_REPLAN_TIMEOUT_S = 0.05
        try:
            result = await adapter.micro_replan(_make_micro_replan_request())
        finally:
            mod._MICRO_REPLAN_TIMEOUT_S = original

        assert result is None
        # CB should be tripped after timeout
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_micro_replan_cb_open(self) -> None:
        mailbox = FakePlannerMailbox()
        cb = _make_cb(state=CircuitBreakerState.OPEN)
        adapter = PlannerAdapter(mailbox, cb)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.micro_replan(_make_micro_replan_request())
        assert exc_info.value.detail.error_code == "CB_PLANNER_OPEN"

    @pytest.mark.asyncio
    async def test_micro_replan_failure_raises(self) -> None:
        mailbox = FakePlannerMailbox(
            micro_replan_error=RuntimeError("planner crashed"),
        )
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.micro_replan(_make_micro_replan_request())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.error_code == "PLANNER_ERROR"
        assert cb.state == CircuitBreakerState.OPEN


class TestPlannerAdapterCBIntegration:
    """CB trip/reset lifecycle through adapter operations."""

    @pytest.mark.asyncio
    async def test_successful_request_resets_cb(self) -> None:
        """After a successful request_plan, CB is CLOSED."""
        mailbox = FakePlannerMailbox()
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        await adapter.request_plan(_make_plan_request())
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_failed_enqueue_trips_cb(self) -> None:
        mailbox = FakePlannerMailbox(enqueue_error=RuntimeError("fail"))
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        await adapter.request_plan(_make_plan_request())
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_successful_micro_replan_resets_cb(self) -> None:
        mailbox = FakePlannerMailbox(
            micro_replan_result=_make_committed_plan(),
        )
        cb = _make_cb()
        adapter = PlannerAdapter(mailbox, cb)

        await adapter.micro_replan(_make_micro_replan_request())
        assert cb.state == CircuitBreakerState.CLOSED


# ===========================================================================
# 6.1.4 -- StateReadAdapter tests
# ===========================================================================


class TestStateReadSection:
    """read_section() -- success, not found, error."""

    @pytest.mark.asyncio
    async def test_read_section_found(self) -> None:
        reader = FakeStateReader(
            sections={"sess-1": {"control": {"safety_band": "GREEN"}}},
        )
        adapter = StateReadAdapter(reader)

        result = await adapter.read_section("sess-1", "control")
        assert result == {"safety_band": "GREEN"}

    @pytest.mark.asyncio
    async def test_read_section_not_found(self) -> None:
        reader = FakeStateReader(sections={"sess-1": {}})
        adapter = StateReadAdapter(reader)

        result = await adapter.read_section("sess-1", "beliefs")
        assert result is None

    @pytest.mark.asyncio
    async def test_read_section_session_not_found(self) -> None:
        reader = FakeStateReader(sections={})
        adapter = StateReadAdapter(reader)

        result = await adapter.read_section("nonexistent", "control")
        assert result is None

    @pytest.mark.asyncio
    async def test_read_section_error(self) -> None:
        reader = FakeStateReader(error=RuntimeError("db down"))
        adapter = StateReadAdapter(reader)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.read_section("sess-1", "control")
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.adapter_name == "state_read"
        assert err.error_code == "STATE_READ_ERROR"


class TestStateReadSections:
    """read_sections() -- success, error."""

    @pytest.mark.asyncio
    async def test_read_sections_success(self) -> None:
        reader = FakeStateReader(
            sections={
                "sess-1": {
                    "control": {"safety_band": "GREEN"},
                    "beliefs": {"topic": "weather"},
                    "persona": {"name": "Alice"},
                },
            },
        )
        adapter = StateReadAdapter(reader)

        result = await adapter.read_sections("sess-1", ["control", "beliefs"])
        assert "control" in result
        assert "beliefs" in result
        assert "persona" not in result

    @pytest.mark.asyncio
    async def test_read_sections_missing_omitted(self) -> None:
        reader = FakeStateReader(
            sections={"sess-1": {"control": {"safety_band": "GREEN"}}},
        )
        adapter = StateReadAdapter(reader)

        result = await adapter.read_sections("sess-1", ["control", "nonexistent"])
        assert "control" in result
        assert "nonexistent" not in result

    @pytest.mark.asyncio
    async def test_read_sections_error(self) -> None:
        reader = FakeStateReader(error=RuntimeError("fail"))
        adapter = StateReadAdapter(reader)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.read_sections("sess-1", ["control"])
        assert exc_info.value.detail.operation == "read_sections"


class TestStateReadSnapshot:
    """get_snapshot() -- success, error."""

    @pytest.mark.asyncio
    async def test_get_snapshot_success(self) -> None:
        reader = FakeStateReader(
            sections={
                "sess-1": {
                    "control": {"safety_band": "GREEN"},
                    "beliefs": {"active": True},
                },
            },
        )
        adapter = StateReadAdapter(reader)

        snap = await adapter.get_snapshot("sess-1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "sess-1"
        assert "control" in snap.sections
        assert "beliefs" in snap.sections

    @pytest.mark.asyncio
    async def test_get_snapshot_empty_session(self) -> None:
        reader = FakeStateReader(sections={})
        adapter = StateReadAdapter(reader)

        snap = await adapter.get_snapshot("nonexistent")
        assert snap.session_id == "nonexistent"
        assert snap.sections == {}

    @pytest.mark.asyncio
    async def test_get_snapshot_error(self) -> None:
        reader = FakeStateReader(error=RuntimeError("crash"))
        adapter = StateReadAdapter(reader)

        with pytest.raises(AdapterException) as exc_info:
            await adapter.get_snapshot("sess-1")
        assert exc_info.value.detail.operation == "get_snapshot"


class TestStateReadNoWriteMethods:
    """ORCH-01: StateReadAdapter exposes NO write methods."""

    def test_no_write_method(self) -> None:
        adapter = StateReadAdapter(FakeStateReader())
        for attr in ("write", "write_section", "set_section", "update", "delete"):
            assert not hasattr(adapter, attr), f"ORCH-01 violation: {attr} exists"

    def test_slots_only_reader(self) -> None:
        adapter = StateReadAdapter(FakeStateReader())
        assert hasattr(adapter, "__slots__")
        assert "_reader" in adapter.__slots__


# ===========================================================================
# Re-exports
# ===========================================================================


class TestAdaptersReExports:
    """Verify adapters/__init__.py re-exports new adapters."""

    def test_planner_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import PlannerAdapter

        assert PlannerAdapter is not None

    def test_state_read_adapter_importable(self) -> None:
        from k1.orchestrator.adapters import StateReadAdapter

        assert StateReadAdapter is not None
