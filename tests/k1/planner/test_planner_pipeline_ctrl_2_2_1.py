"""Tests for PipelineController skeleton & constructor (Issue 2.2.1).

Tests cover:
  - Constructor with valid dependencies (7 params)
  - Constructor None-rejection for each dependency
  - FSM wiring (on_transition callback connected to _on_fsm_transition)
  - reset() method (counters cleared, FSM to IDLE)
  - Properties (read-only access to internal state)
  - _on_fsm_transition callback (delta emission, logging, exception safety)
  - Layer 2 import validation
  - __all__ export verification

References
----------
- planner.md Section 17.2 (PipelineController ~80 tests)
- planner.md Section 23.2 (PLAN_START lifecycle -- reset())
- planner.md Section 30.5.1 F03 (pipeline_controller.py spec)
- planner.md Section 30.6 (Dependency Layers)
- docs/plans/planner-implementation-plan.md Issue 2.2.1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.pipeline_controller import PipelineController
from k1.planner.plan_fsm import PlanState, PlanStateMachine
from k1.planner.types import (
    DELTA_STAGE_TRANSITION,
    PLANNER_AGENT_ID,
    SECTION_PIPELINE,
    DeltaPayload,
    StagePhase,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeDeltaPort:
    """Minimal IDeltaEmitPort implementation that records emitted deltas."""

    def __init__(self) -> None:
        self.emitted: List[DeltaPayload] = []

    def emit(self, delta: DeltaPayload) -> None:
        self.emitted.append(delta)


class FailingDeltaPort:
    """IDeltaEmitPort that raises on every emit (for callback safety tests)."""

    def emit(self, delta: DeltaPayload) -> None:
        raise RuntimeError("Delta bus unavailable")


class FakeEventPort:
    """Minimal IEventPort implementation that records emitted events."""

    def __init__(self) -> None:
        self.emitted: List[Tuple[str, Dict[str, Any]]] = []
        self.subscriptions: List[Tuple[str, Any]] = []

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> Any:
        self.subscriptions.append((topic, handler))
        return f"sub-{topic}"

    def unsubscribe(self, handle: Any) -> None:
        pass


class FakeService:
    """Minimal stub for stage services (SketchService, etc.)."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name


@dataclass
class FakePlanRequest:
    """Minimal stand-in for PlanRequest (from k1.orchestrator.types)."""

    request_id: str = "req-001"
    trace_id: str = "trace-abc"
    intent: str = "test intent"


def _make_controller(
    *,
    sketch: Any = None,
    expand: Any = None,
    validate: Any = None,
    commit: Any = None,
    delta_port: Any = None,
    event_port: Any = None,
    config: Any = None,
) -> PipelineController:
    """Helper to construct PipelineController with defaults for unspecified params."""
    return PipelineController(
        sketch=sketch if sketch is not None else FakeService("sketch"),
        expand=expand if expand is not None else FakeService("expand"),
        validate=validate if validate is not None else FakeService("validate"),
        commit=commit if commit is not None else FakeService("commit"),
        delta_port=delta_port if delta_port is not None else FakeDeltaPort(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


# ===========================================================================
# 1. Constructor -- valid dependencies
# ===========================================================================


class TestConstructorValid:
    """Constructor accepts 7 injected dependencies and initialises state."""

    def test_constructor_stores_sketch_service(self) -> None:
        sketch = FakeService("sketch")
        ctrl = _make_controller(sketch=sketch)
        assert ctrl._sketch is sketch

    def test_constructor_stores_expand_service(self) -> None:
        expand = FakeService("expand")
        ctrl = _make_controller(expand=expand)
        assert ctrl._expand is expand

    def test_constructor_stores_validate_service(self) -> None:
        validate = FakeService("validate")
        ctrl = _make_controller(validate=validate)
        assert ctrl._validate is validate

    def test_constructor_stores_commit_service(self) -> None:
        commit = FakeService("commit")
        ctrl = _make_controller(commit=commit)
        assert ctrl._commit is commit

    def test_constructor_stores_delta_port(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        assert ctrl._delta_port is dp

    def test_constructor_stores_event_port(self) -> None:
        ep = FakeEventPort()
        ctrl = _make_controller(event_port=ep)
        assert ctrl._event_port is ep

    def test_constructor_stores_config(self) -> None:
        cfg = PlannerConfig()
        ctrl = _make_controller(config=cfg)
        assert ctrl._config is cfg
        assert ctrl.config is cfg

    def test_constructor_creates_fsm_instance(self) -> None:
        ctrl = _make_controller()
        assert isinstance(ctrl._fsm, PlanStateMachine)

    def test_constructor_fsm_starts_idle(self) -> None:
        ctrl = _make_controller()
        assert ctrl._fsm.current_state == PlanState.IDLE
        assert ctrl.current_state == PlanState.IDLE

    def test_constructor_initial_token_usage_empty(self) -> None:
        ctrl = _make_controller()
        assert ctrl._stage_token_usage == {}

    def test_constructor_initial_stage_cost_empty(self) -> None:
        ctrl = _make_controller()
        assert ctrl._stage_cost == {}

    def test_constructor_initial_stage_latency_empty(self) -> None:
        ctrl = _make_controller()
        assert ctrl._stage_latency == {}

    def test_constructor_initial_total_plan_tokens_zero(self) -> None:
        ctrl = _make_controller()
        assert ctrl._total_plan_tokens == 0
        assert ctrl.total_plan_tokens == 0

    def test_constructor_initial_tool_call_count_zero(self) -> None:
        ctrl = _make_controller()
        assert ctrl._tool_call_count == 0
        assert ctrl.tool_call_count == 0

    def test_constructor_initial_hil_round_count_zero(self) -> None:
        ctrl = _make_controller()
        assert ctrl._hil_round_count == 0
        assert ctrl.hil_round_count == 0

    def test_constructor_initial_current_request_none(self) -> None:
        ctrl = _make_controller()
        assert ctrl._current_request is None
        assert ctrl.current_request is None

    def test_constructor_initial_plan_start_time_none(self) -> None:
        ctrl = _make_controller()
        assert ctrl._plan_start_time is None
        assert ctrl.plan_start_time is None

    def test_constructor_initial_revise_count_zero(self) -> None:
        ctrl = _make_controller()
        assert ctrl._revise_count == 0
        assert ctrl.revise_count == 0


# ===========================================================================
# 2. Constructor -- None rejection (all 7 dependencies)
# ===========================================================================


class TestConstructorNoneRejection:
    """Constructor raises ValueError if any dependency is None."""

    def test_none_sketch_raises(self) -> None:
        with pytest.raises(ValueError, match="sketch service must not be None"):
            PipelineController(
                sketch=None,
                expand=FakeService(),
                validate=FakeService(),
                commit=FakeService(),
                delta_port=FakeDeltaPort(),
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_expand_raises(self) -> None:
        with pytest.raises(ValueError, match="expand service must not be None"):
            PipelineController(
                sketch=FakeService(),
                expand=None,
                validate=FakeService(),
                commit=FakeService(),
                delta_port=FakeDeltaPort(),
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_validate_raises(self) -> None:
        with pytest.raises(ValueError, match="validate service must not be None"):
            PipelineController(
                sketch=FakeService(),
                expand=FakeService(),
                validate=None,
                commit=FakeService(),
                delta_port=FakeDeltaPort(),
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_commit_raises(self) -> None:
        with pytest.raises(ValueError, match="commit service must not be None"):
            PipelineController(
                sketch=FakeService(),
                expand=FakeService(),
                validate=FakeService(),
                commit=None,
                delta_port=FakeDeltaPort(),
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_delta_port_raises(self) -> None:
        with pytest.raises(ValueError, match="delta_port must not be None"):
            PipelineController(
                sketch=FakeService(),
                expand=FakeService(),
                validate=FakeService(),
                commit=FakeService(),
                delta_port=None,
                event_port=FakeEventPort(),
                config=PlannerConfig(),
            )

    def test_none_event_port_raises(self) -> None:
        with pytest.raises(ValueError, match="event_port must not be None"):
            PipelineController(
                sketch=FakeService(),
                expand=FakeService(),
                validate=FakeService(),
                commit=FakeService(),
                delta_port=FakeDeltaPort(),
                event_port=None,
                config=PlannerConfig(),
            )

    def test_none_config_raises(self) -> None:
        with pytest.raises(ValueError, match="config must not be None"):
            PipelineController(
                sketch=FakeService(),
                expand=FakeService(),
                validate=FakeService(),
                commit=FakeService(),
                delta_port=FakeDeltaPort(),
                event_port=FakeEventPort(),
                config=None,
            )


# ===========================================================================
# 3. FSM wiring (on_transition callback)
# ===========================================================================


class TestFSMWiring:
    """Verify PlanStateMachine is wired with _on_fsm_transition callback."""

    def test_fsm_callback_is_connected(self) -> None:
        """PlanStateMachine._on_transition points to PipelineController._on_fsm_transition."""
        ctrl = _make_controller()
        assert ctrl._fsm._on_transition is not None
        assert ctrl._fsm._on_transition == ctrl._on_fsm_transition

    def test_fsm_transition_fires_callback(self) -> None:
        """Legal FSM transition invokes _on_fsm_transition -> emits delta."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        # Set a current_request so trace_id is available
        ctrl._current_request = FakePlanRequest()
        # Transition IDLE -> SKETCHING
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="plan_start")
        assert len(dp.emitted) == 1
        delta = dp.emitted[0]
        assert delta.agent_id == PLANNER_AGENT_ID
        assert delta.delta_type == DELTA_STAGE_TRANSITION
        assert delta.section == SECTION_PIPELINE
        assert delta.data["from_state"] == "IDLE"
        assert delta.data["to_state"] == "SKETCHING"
        assert delta.data["trigger"] == "plan_start"
        assert delta.trace_id == "trace-abc"

    def test_fsm_transition_without_request_uses_unknown_trace(self) -> None:
        """When _current_request is None, trace_id defaults to 'unknown'."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="no_request")
        assert len(dp.emitted) == 1
        assert dp.emitted[0].trace_id == "unknown"

    def test_fsm_multiple_transitions_emit_multiple_deltas(self) -> None:
        """Multiple transitions produce one delta each."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        ctrl._fsm.transition(PlanState.EXPANDING, trigger="sketch_done")
        ctrl._fsm.transition(PlanState.VALIDATING, trigger="expand_done")
        assert len(dp.emitted) == 3
        assert dp.emitted[0].data["to_state"] == "SKETCHING"
        assert dp.emitted[1].data["to_state"] == "EXPANDING"
        assert dp.emitted[2].data["to_state"] == "VALIDATING"

    def test_force_failed_fires_callback(self) -> None:
        """force_failed() also invokes the on_transition callback."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        dp.emitted.clear()
        ctrl._fsm.force_failed(trigger="uncaught_error")
        assert len(dp.emitted) == 1
        assert dp.emitted[0].data["from_state"] == "SKETCHING"
        assert dp.emitted[0].data["to_state"] == "FAILED"
        assert dp.emitted[0].data["trigger"] == "uncaught_error"

    def test_force_cancelled_fires_callback(self) -> None:
        """force_cancelled() also invokes the on_transition callback."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        dp.emitted.clear()
        ctrl._fsm.force_cancelled(trigger="user_cancel")
        assert len(dp.emitted) == 1
        assert dp.emitted[0].data["from_state"] == "SKETCHING"
        assert dp.emitted[0].data["to_state"] == "CANCELLED"

    def test_reset_does_not_fire_callback(self) -> None:
        """FSM reset() does NOT invoke on_transition (per spec SS18.6)."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        ctrl._fsm.force_failed(trigger="err")
        dp.emitted.clear()
        ctrl._fsm.reset()
        assert len(dp.emitted) == 0


# ===========================================================================
# 4. _on_fsm_transition callback safety
# ===========================================================================


class TestCallbackSafety:
    """on_transition callback is wrapped in try/except -- never blocks pipeline."""

    def test_failing_delta_port_does_not_raise(self) -> None:
        """If delta_port.emit() raises, callback swallows and logs."""
        ctrl = _make_controller(delta_port=FailingDeltaPort())
        ctrl._current_request = FakePlanRequest()
        # Should NOT raise
        ctrl._on_fsm_transition(PlanState.IDLE, PlanState.SKETCHING, "test")

    def test_failing_delta_port_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Callback failure is logged as a warning."""
        ctrl = _make_controller(delta_port=FailingDeltaPort())
        ctrl._current_request = FakePlanRequest()
        with caplog.at_level(logging.WARNING, logger="k1.planner.pipeline_controller"):
            ctrl._on_fsm_transition(PlanState.IDLE, PlanState.SKETCHING, "test")
        assert any("transition_callback_failed" in r.message for r in caplog.records)

    def test_callback_with_none_request_uses_empty_strings(self) -> None:
        """With _current_request None, callback uses empty request_id and 'unknown' trace."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        # _current_request is None by default
        ctrl._on_fsm_transition(PlanState.IDLE, PlanState.SKETCHING, "init")
        assert len(dp.emitted) == 1
        delta = dp.emitted[0]
        assert delta.trace_id == "unknown"

    def test_callback_with_request_missing_trace_id(self) -> None:
        """If request has no trace_id attr, gracefully defaults."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = object()  # No trace_id attribute
        ctrl._on_fsm_transition(PlanState.IDLE, PlanState.SKETCHING, "init")
        assert len(dp.emitted) == 1
        # getattr returns "" for missing attr, then "unknown" fallback
        assert dp.emitted[0].trace_id == "unknown"


# ===========================================================================
# 5. reset() method
# ===========================================================================


class TestReset:
    """reset() clears all per-plan state per Section 23.2 step 4."""

    def test_reset_from_idle_is_idempotent(self) -> None:
        """reset() when FSM is IDLE is a no-op on FSM but still clears counters."""
        ctrl = _make_controller()
        ctrl.reset()
        assert ctrl.current_state == PlanState.IDLE
        assert ctrl._stage_token_usage == {
            "SKETCH": 0,
            "EXPAND": 0,
            "VALIDATE": 0,
            "COMMIT": 0,
        }

    def test_reset_from_completed_transitions_to_idle(self) -> None:
        """reset() from COMPLETED resets FSM to IDLE."""
        ctrl = _make_controller()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        ctrl._fsm.transition(PlanState.EXPANDING, trigger="sketch_done")
        ctrl._fsm.transition(PlanState.VALIDATING, trigger="expand_done")
        ctrl._fsm.transition(PlanState.COMMITTING, trigger="validate_done")
        ctrl._fsm.transition(PlanState.COMPLETED, trigger="commit_done")
        ctrl.reset()
        assert ctrl.current_state == PlanState.IDLE

    def test_reset_from_failed_transitions_to_idle(self) -> None:
        """reset() from FAILED resets FSM to IDLE."""
        ctrl = _make_controller()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        ctrl._fsm.force_failed(trigger="error")
        ctrl.reset()
        assert ctrl.current_state == PlanState.IDLE

    def test_reset_from_cancelled_transitions_to_idle(self) -> None:
        """reset() from CANCELLED resets FSM to IDLE."""
        ctrl = _make_controller()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        ctrl._fsm.force_cancelled(trigger="cancel")
        ctrl.reset()
        assert ctrl.current_state == PlanState.IDLE

    def test_reset_clears_stage_token_usage(self) -> None:
        """After reset(), _stage_token_usage has 4 keys all at 0."""
        ctrl = _make_controller()
        ctrl._stage_token_usage = {"SKETCH": 500, "EXPAND": 300}
        ctrl.reset()
        assert ctrl._stage_token_usage == {
            "SKETCH": 0,
            "EXPAND": 0,
            "VALIDATE": 0,
            "COMMIT": 0,
        }

    def test_reset_clears_stage_cost(self) -> None:
        """After reset(), _stage_cost has 4 keys all at 0.0."""
        ctrl = _make_controller()
        ctrl._stage_cost = {"SKETCH": 0.5}
        ctrl.reset()
        assert ctrl._stage_cost == {
            "SKETCH": 0.0,
            "EXPAND": 0.0,
            "VALIDATE": 0.0,
            "COMMIT": 0.0,
        }

    def test_reset_clears_stage_latency(self) -> None:
        """After reset(), _stage_latency has 4 keys all at 0."""
        ctrl = _make_controller()
        ctrl._stage_latency = {"SKETCH": 1000}
        ctrl.reset()
        assert ctrl._stage_latency == {
            "SKETCH": 0,
            "EXPAND": 0,
            "VALIDATE": 0,
            "COMMIT": 0,
        }

    def test_reset_clears_total_plan_tokens(self) -> None:
        ctrl = _make_controller()
        ctrl._total_plan_tokens = 2500
        ctrl.reset()
        assert ctrl._total_plan_tokens == 0
        assert ctrl.total_plan_tokens == 0

    def test_reset_clears_tool_call_count(self) -> None:
        ctrl = _make_controller()
        ctrl._tool_call_count = 5
        ctrl.reset()
        assert ctrl._tool_call_count == 0
        assert ctrl.tool_call_count == 0

    def test_reset_clears_hil_round_count(self) -> None:
        ctrl = _make_controller()
        ctrl._hil_round_count = 2
        ctrl.reset()
        assert ctrl._hil_round_count == 0
        assert ctrl.hil_round_count == 0

    def test_reset_clears_current_request(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl.reset()
        assert ctrl._current_request is None
        assert ctrl.current_request is None

    def test_reset_clears_plan_start_time(self) -> None:
        ctrl = _make_controller()
        ctrl._plan_start_time = 12345.0
        ctrl.reset()
        assert ctrl._plan_start_time is None
        assert ctrl.plan_start_time is None

    def test_reset_clears_revise_count(self) -> None:
        ctrl = _make_controller()
        ctrl._revise_count = 1
        ctrl.reset()
        assert ctrl._revise_count == 0
        assert ctrl.revise_count == 0

    def test_reset_stage_token_usage_keys_match_stage_phase(self) -> None:
        """Stage token usage keys match StagePhase enum values."""
        ctrl = _make_controller()
        ctrl.reset()
        expected_keys = {sp.value for sp in StagePhase}
        assert set(ctrl._stage_token_usage.keys()) == expected_keys

    def test_reset_preserves_injected_dependencies(self) -> None:
        """reset() does NOT clear injected dependencies (services, ports, config)."""
        sketch = FakeService("s")
        expand = FakeService("e")
        validate = FakeService("v")
        commit = FakeService("c")
        dp = FakeDeltaPort()
        ep = FakeEventPort()
        cfg = PlannerConfig()
        ctrl = _make_controller(
            sketch=sketch,
            expand=expand,
            validate=validate,
            commit=commit,
            delta_port=dp,
            event_port=ep,
            config=cfg,
        )
        ctrl.reset()
        assert ctrl._sketch is sketch
        assert ctrl._expand is expand
        assert ctrl._validate is validate
        assert ctrl._commit is commit
        assert ctrl._delta_port is dp
        assert ctrl._event_port is ep
        assert ctrl._config is cfg

    def test_reset_preserves_fsm_instance(self) -> None:
        """reset() resets FSM state but does NOT replace the FSM instance."""
        ctrl = _make_controller()
        fsm = ctrl._fsm
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        ctrl._fsm.force_failed(trigger="err")
        ctrl.reset()
        assert ctrl._fsm is fsm  # Same instance
        assert ctrl._fsm.current_state == PlanState.IDLE

    def test_double_reset_from_idle(self) -> None:
        """Calling reset() twice from IDLE is safe."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl.reset()
        assert ctrl.current_state == PlanState.IDLE


# ===========================================================================
# 6. Properties
# ===========================================================================


class TestProperties:
    """Read-only properties expose internal state correctly."""

    def test_current_state_reflects_fsm(self) -> None:
        ctrl = _make_controller()
        assert ctrl.current_state == PlanState.IDLE
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        assert ctrl.current_state == PlanState.SKETCHING

    def test_config_returns_injected_config(self) -> None:
        cfg = PlannerConfig(mailbox_max_depth=3)
        ctrl = _make_controller(config=cfg)
        assert ctrl.config is cfg
        assert ctrl.config.mailbox_max_depth == 3

    def test_stage_token_usage_returns_copy(self) -> None:
        """stage_token_usage property returns a copy, not the internal dict."""
        ctrl = _make_controller()
        ctrl.reset()
        usage = ctrl.stage_token_usage
        usage["SKETCH"] = 9999  # Mutate the copy
        assert ctrl._stage_token_usage["SKETCH"] == 0  # Internal unchanged

    def test_total_plan_tokens_reflects_internal(self) -> None:
        ctrl = _make_controller()
        ctrl._total_plan_tokens = 1234
        assert ctrl.total_plan_tokens == 1234

    def test_tool_call_count_reflects_internal(self) -> None:
        ctrl = _make_controller()
        ctrl._tool_call_count = 4
        assert ctrl.tool_call_count == 4

    def test_hil_round_count_reflects_internal(self) -> None:
        ctrl = _make_controller()
        ctrl._hil_round_count = 2
        assert ctrl.hil_round_count == 2

    def test_revise_count_reflects_internal(self) -> None:
        ctrl = _make_controller()
        ctrl._revise_count = 1
        assert ctrl.revise_count == 1

    def test_plan_start_time_reflects_internal(self) -> None:
        ctrl = _make_controller()
        ctrl._plan_start_time = 99.9
        assert ctrl.plan_start_time == 99.9

    def test_current_request_reflects_internal(self) -> None:
        req = FakePlanRequest()
        ctrl = _make_controller()
        ctrl._current_request = req
        assert ctrl.current_request is req


# ===========================================================================
# 7. __slots__ validation
# ===========================================================================


class TestSlots:
    """PipelineController uses __slots__ for memory efficiency."""

    def test_has_slots(self) -> None:
        assert hasattr(PipelineController, "__slots__")

    def test_cannot_set_arbitrary_attribute(self) -> None:
        """__slots__ prevents dynamic attribute creation."""
        ctrl = _make_controller()
        with pytest.raises(AttributeError):
            ctrl.nonexistent_attr = "should_fail"  # type: ignore[attr-defined]

    def test_all_slots_present(self) -> None:
        """All expected slots are declared."""
        expected = {
            "_sketch",
            "_expand",
            "_validate",
            "_commit",
            "_delta_port",
            "_event_port",
            "_config",
            "_fsm",
            "_stage_token_usage",
            "_stage_cost",
            "_stage_latency",
            "_total_plan_tokens",
            "_tool_call_count",
            "_hil_round_count",
            "_current_request",
            "_plan_start_time",
            "_revise_count",
            "_active_cancel_check",
        }
        assert set(PipelineController.__slots__) == expected


# ===========================================================================
# 8. Custom config values propagated
# ===========================================================================


class TestConfigPropagation:
    """Constructor accepts custom PlannerConfig and makes it accessible."""

    def test_custom_pipeline_timeout(self) -> None:
        cfg = PlannerConfig(pipeline_timeout_ms=30_000)
        ctrl = _make_controller(config=cfg)
        assert ctrl.config.pipeline_timeout_ms == 30_000

    def test_custom_token_budgets(self) -> None:
        cfg = PlannerConfig(
            sketch_max_tokens=4000,
            expand_max_tokens=2000,
            validate_max_tokens=1000,
            total_token_budget=7000,
        )
        ctrl = _make_controller(config=cfg)
        assert ctrl.config.sketch_max_tokens == 4000
        assert ctrl.config.expand_max_tokens == 2000
        assert ctrl.config.validate_max_tokens == 1000
        assert ctrl.config.total_token_budget == 7000

    def test_custom_temperatures(self) -> None:
        cfg = PlannerConfig(
            sketch_temperature=0.9, expand_temperature=0.5, validate_temperature=0.1
        )
        ctrl = _make_controller(config=cfg)
        assert ctrl.config.sketch_temperature == 0.9
        assert ctrl.config.expand_temperature == 0.5
        assert ctrl.config.validate_temperature == 0.1

    def test_custom_micro_replan_settings(self) -> None:
        cfg = PlannerConfig(
            micro_replan_timeout_ms=5_000,
            micro_replan_max_tokens=2_500,
            micro_sketch_max_tokens=1_200,
            micro_expand_max_tokens=800,
            micro_validate_max_tokens=400,
        )
        ctrl = _make_controller(config=cfg)
        assert ctrl.config.micro_replan_timeout_ms == 5_000
        assert ctrl.config.micro_replan_max_tokens == 2_500


# ===========================================================================
# 9. Delta emission content validation
# ===========================================================================


class TestDeltaEmissionContent:
    """Verify emitted deltas have correct structure per SS22.4.1."""

    def test_delta_agent_id_is_planner(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        assert dp.emitted[0].agent_id == "planner"

    def test_delta_type_is_stage_transition(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        assert dp.emitted[0].delta_type == "stage_transition"

    def test_delta_section_is_pipeline(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        assert dp.emitted[0].section == "pipeline"

    def test_delta_data_contains_from_to_trigger(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="my_trigger")
        data = dp.emitted[0].data
        assert "from_state" in data
        assert "to_state" in data
        assert "trigger" in data
        assert data["trigger"] == "my_trigger"

    def test_delta_trace_id_from_request(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest(trace_id="trace-xyz")
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="start")
        assert dp.emitted[0].trace_id == "trace-xyz"

    def test_full_pipeline_transitions_emit_correct_state_sequence(self) -> None:
        """Simulate full 4-stage pipeline transitions and verify delta sequence."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        transitions = [
            (PlanState.SKETCHING, "plan_start"),
            (PlanState.EXPANDING, "sketch_done"),
            (PlanState.VALIDATING, "expand_done"),
            (PlanState.COMMITTING, "validate_done"),
            (PlanState.COMPLETED, "commit_done"),
        ]
        for state, trigger in transitions:
            ctrl._fsm.transition(state, trigger=trigger)

        assert len(dp.emitted) == 5
        expected_sequence = [
            ("IDLE", "SKETCHING"),
            ("SKETCHING", "EXPANDING"),
            ("EXPANDING", "VALIDATING"),
            ("VALIDATING", "COMMITTING"),
            ("COMMITTING", "COMPLETED"),
        ]
        for i, (expected_from, expected_to) in enumerate(expected_sequence):
            assert dp.emitted[i].data["from_state"] == expected_from
            assert dp.emitted[i].data["to_state"] == expected_to

    def test_micro_replan_transitions_emit_correct_state_sequence(self) -> None:
        """Simulate micro-replan 3-stage transitions (plus commit)."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        transitions = [
            (PlanState.MICRO_SKETCH, "micro_start"),
            (PlanState.MICRO_EXPAND, "micro_sketch_done"),
            (PlanState.MICRO_VALIDATE, "micro_expand_done"),
            (PlanState.COMMITTING, "micro_validate_done"),
            (PlanState.COMPLETED, "commit_done"),
        ]
        for state, trigger in transitions:
            ctrl._fsm.transition(state, trigger=trigger)

        assert len(dp.emitted) == 5
        expected = [
            ("IDLE", "MICRO_SKETCH"),
            ("MICRO_SKETCH", "MICRO_EXPAND"),
            ("MICRO_EXPAND", "MICRO_VALIDATE"),
            ("MICRO_VALIDATE", "COMMITTING"),
            ("COMMITTING", "COMPLETED"),
        ]
        for i, (ef, et) in enumerate(expected):
            assert dp.emitted[i].data["from_state"] == ef
            assert dp.emitted[i].data["to_state"] == et


# ===========================================================================
# 10. Structured logging
# ===========================================================================


class TestStructuredLogging:
    """Verify _on_fsm_transition emits structured logs."""

    def test_transition_logs_info(self, caplog: pytest.LogCaptureFixture) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest(request_id="req-123", trace_id="tr-456")
        with caplog.at_level(logging.INFO, logger="k1.planner.pipeline_controller"):
            ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")
        assert any("fsm.transition" in r.message for r in caplog.records)

    def test_transition_log_contains_extra_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest(request_id="req-123", trace_id="tr-456")
        with caplog.at_level(logging.INFO, logger="k1.planner.pipeline_controller"):
            ctrl._fsm.transition(PlanState.SKETCHING, trigger="test_trigger")
        records = [r for r in caplog.records if r.message == "fsm.transition"]
        assert len(records) >= 1
        r = records[0]
        assert r.from_state == "IDLE"  # type: ignore[attr-defined]
        assert r.to_state == "SKETCHING"  # type: ignore[attr-defined]
        assert r.trigger == "test_trigger"  # type: ignore[attr-defined]
        assert r.trace_id == "tr-456"  # type: ignore[attr-defined]
        assert r.request_id == "req-123"  # type: ignore[attr-defined]


# ===========================================================================
# 11. Layer 2 import validation (SS30.6)
# ===========================================================================


class TestImportLayer:
    """PipelineController is Layer 5 (SS30.6).  Verify import structure."""

    def test_import_from_pipeline_controller_module(self) -> None:
        """Can import PipelineController from its own module."""
        from k1.planner.pipeline_controller import PipelineController as PC

        assert PC is PipelineController

    def test_import_from_planner_package(self) -> None:
        """Can import PipelineController from k1.planner package (__init__.py)."""
        from k1.planner import PipelineController as PC

        assert PC is PipelineController

    def test_pipeline_controller_does_not_import_planner_agent(self) -> None:
        """Layer 5 does NOT import from Layer 6 (planner_agent.py)."""
        import inspect
        import re

        import k1.planner.pipeline_controller as mod

        source = inspect.getsource(mod)
        # Check for actual import statements, not docstring references
        import_lines = [
            line.strip() for line in source.splitlines() if re.match(r"^\s*(from|import)\s+", line)
        ]
        for line in import_lines:
            assert (
                "planner_agent" not in line
            ), f"Layer 5 must not import from planner_agent: {line}"

    def test_pipeline_controller_does_not_import_factory(self) -> None:
        """Layer 5 does NOT import from Layer 7 (factory.py)."""
        import inspect
        import re

        import k1.planner.pipeline_controller as mod

        source = inspect.getsource(mod)
        # Check for actual import statements, not docstring references
        import_lines = [
            line.strip() for line in source.splitlines() if re.match(r"^\s*(from|import)\s+", line)
        ]
        for line in import_lines:
            assert "factory" not in line, f"Layer 5 must not import from factory: {line}"

    def test_pipeline_controller_imports_only_lower_layers(self) -> None:
        """Verify all imports are from Layer 0-1 (types, plan_fsm, config, ports)."""
        import inspect

        import k1.planner.pipeline_controller as mod

        source = inspect.getsource(mod)
        # Must import from these Layer 0-1 modules
        assert "k1.planner.config" in source
        assert "k1.planner.plan_fsm" in source
        assert "k1.planner.types" in source
        assert "k1.planner.ports" in source


# ===========================================================================
# 12. __all__ export
# ===========================================================================


class TestExports:
    """Verify __all__ is correct and complete."""

    def test_pipeline_controller_in_all(self) -> None:
        from k1.planner.pipeline_controller import __all__ as pc_all

        assert "PipelineController" in pc_all

    def test_pipeline_controller_in_package_all(self) -> None:
        from k1.planner import __all__ as pkg_all

        assert "PipelineController" in pkg_all

    def test_all_contains_only_pipeline_controller(self) -> None:
        """__all__ in pipeline_controller.py has exactly one entry (skeleton)."""
        from k1.planner.pipeline_controller import __all__ as pc_all

        assert pc_all == ["PipelineController"]


# ===========================================================================
# 13. Multiple controller instances are independent
# ===========================================================================


class TestInstanceIndependence:
    """Multiple PipelineController instances do not share state."""

    def test_separate_fsm_instances(self) -> None:
        ctrl1 = _make_controller()
        ctrl2 = _make_controller()
        ctrl1._fsm.transition(PlanState.SKETCHING, trigger="ctrl1")
        assert ctrl1.current_state == PlanState.SKETCHING
        assert ctrl2.current_state == PlanState.IDLE

    def test_separate_delta_ports(self) -> None:
        dp1 = FakeDeltaPort()
        dp2 = FakeDeltaPort()
        ctrl1 = _make_controller(delta_port=dp1)
        ctrl2 = _make_controller(delta_port=dp2)
        ctrl1._current_request = FakePlanRequest()
        ctrl1._fsm.transition(PlanState.SKETCHING, trigger="test")
        assert len(dp1.emitted) == 1
        assert len(dp2.emitted) == 0

    def test_separate_counters(self) -> None:
        ctrl1 = _make_controller()
        ctrl2 = _make_controller()
        ctrl1._total_plan_tokens = 500
        assert ctrl2._total_plan_tokens == 0

    def test_separate_reset(self) -> None:
        ctrl1 = _make_controller()
        ctrl2 = _make_controller()
        ctrl1.reset()
        assert ctrl1._stage_token_usage == {
            "SKETCH": 0,
            "EXPAND": 0,
            "VALIDATE": 0,
            "COMMIT": 0,
        }
        assert ctrl2._stage_token_usage == {}


# ===========================================================================
# 14. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Boundary and edge case tests."""

    def test_empty_trigger_string(self) -> None:
        """FSM transition with empty trigger works correctly."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="")
        assert dp.emitted[0].data["trigger"] == ""

    def test_long_trigger_string(self) -> None:
        """FSM transition with very long trigger preserves it."""
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        ctrl._current_request = FakePlanRequest()
        long_trigger = "x" * 1000
        ctrl._fsm.transition(PlanState.SKETCHING, trigger=long_trigger)
        assert dp.emitted[0].data["trigger"] == long_trigger

    def test_reset_then_transition(self) -> None:
        """After reset(), FSM can transition to SKETCHING."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="new_plan")
        assert ctrl.current_state == PlanState.SKETCHING

    def test_reset_then_transition_to_micro_sketch(self) -> None:
        """After reset(), FSM can transition to MICRO_SKETCH."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._fsm.transition(PlanState.MICRO_SKETCH, trigger="micro_replan")
        assert ctrl.current_state == PlanState.MICRO_SKETCH

    def test_multiple_resets_in_sequence(self) -> None:
        """Multiple resets from IDLE are safe."""
        ctrl = _make_controller()
        for _ in range(5):
            ctrl.reset()
        assert ctrl.current_state == PlanState.IDLE

    def test_service_with_any_type_accepted(self) -> None:
        """Constructor accepts any non-None object as a service."""
        ctrl = PipelineController(
            sketch="not_a_real_service",
            expand=42,
            validate={"key": "val"},
            commit=[1, 2, 3],
            delta_port=FakeDeltaPort(),
            event_port=FakeEventPort(),
            config=PlannerConfig(),
        )
        assert ctrl._sketch == "not_a_real_service"
        assert ctrl._expand == 42
        assert ctrl._validate == {"key": "val"}
        assert ctrl._commit == [1, 2, 3]
        assert ctrl._validate == {"key": "val"}
        assert ctrl._commit == [1, 2, 3]
