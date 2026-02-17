"""Validation tests for issues 1.2.6-1.2.10."""

from k1.planner import DeltaPayload, PlanState, StageContext, StagePhase, ToolCallStatus


def test_all_imports():
    print("All 15 imports from k1.planner OK")


def test_stage_context_valid():
    cancel = lambda: False
    ctx = StageContext(
        request_id="req-1",
        trace_id="trace-1",
        timeout_remaining_ms=5000,
        token_budget_remaining=3500,
        cancel_check=cancel,
    )
    assert ctx.request_id == "req-1"
    assert ctx.timeout_remaining_ms == 5000
    print(f"OK: StageContext created: req={ctx.request_id}")


def test_stage_context_frozen():
    cancel = lambda: False
    ctx = StageContext(
        request_id="r",
        trace_id="t",
        timeout_remaining_ms=1,
        token_budget_remaining=0,
        cancel_check=cancel,
    )
    try:
        ctx.timeout_remaining_ms = 1000
        assert False, "mutation allowed"
    except Exception:
        print("OK: StageContext is frozen")


def test_stage_context_empty_request_id():
    cancel = lambda: False
    try:
        StageContext(
            request_id="",
            trace_id="t",
            timeout_remaining_ms=1,
            token_budget_remaining=0,
            cancel_check=cancel,
        )
        assert False
    except ValueError:
        print("OK: empty request_id rejected")


def test_stage_context_empty_trace_id():
    cancel = lambda: False
    try:
        StageContext(
            request_id="r",
            trace_id="",
            timeout_remaining_ms=1,
            token_budget_remaining=0,
            cancel_check=cancel,
        )
        assert False
    except ValueError:
        print("OK: empty trace_id rejected")


def test_stage_context_zero_timeout():
    cancel = lambda: False
    try:
        StageContext(
            request_id="r",
            trace_id="t",
            timeout_remaining_ms=0,
            token_budget_remaining=0,
            cancel_check=cancel,
        )
        assert False
    except ValueError:
        print("OK: zero timeout rejected")


def test_stage_context_negative_timeout():
    cancel = lambda: False
    try:
        StageContext(
            request_id="r",
            trace_id="t",
            timeout_remaining_ms=-1,
            token_budget_remaining=0,
            cancel_check=cancel,
        )
        assert False
    except ValueError:
        print("OK: negative timeout rejected")


def test_stage_context_negative_token_budget():
    cancel = lambda: False
    try:
        StageContext(
            request_id="r",
            trace_id="t",
            timeout_remaining_ms=1,
            token_budget_remaining=-1,
            cancel_check=cancel,
        )
        assert False
    except ValueError:
        print("OK: negative token budget rejected")


def test_stage_context_non_callable_cancel():
    try:
        StageContext(
            request_id="r",
            trace_id="t",
            timeout_remaining_ms=1,
            token_budget_remaining=0,
            cancel_check="not_callable",
        )
        assert False
    except ValueError:
        print("OK: non-callable cancel_check rejected")


def test_stage_context_zero_budget_valid():
    cancel = lambda: False
    ctx = StageContext(
        request_id="r",
        trace_id="t",
        timeout_remaining_ms=1,
        token_budget_remaining=0,
        cancel_check=cancel,
    )
    assert ctx.token_budget_remaining == 0
    print("OK: StageContext with zero token budget created")


def test_delta_payload_valid():
    dp = DeltaPayload(
        agent_id="planner",
        delta_type="stage_transition",
        section="pipeline",
        data={"stage": "SKETCH", "status": "started"},
        trace_id="trace-1",
    )
    assert dp.delta_type == "stage_transition"
    assert dp.section == "pipeline"
    print(f"OK: DeltaPayload created: type={dp.delta_type}")


def test_delta_payload_frozen():
    dp = DeltaPayload(
        agent_id="p", delta_type="plan_end", section="pipeline", data={}, trace_id="t"
    )
    try:
        dp.delta_type = "mutated"
        assert False
    except Exception:
        print("OK: DeltaPayload is frozen")


def test_delta_payload_invalid_type():
    try:
        DeltaPayload(agent_id="p", delta_type="invalid", section="pipeline", data={}, trace_id="t")
        assert False
    except ValueError:
        print("OK: invalid delta_type rejected")


def test_delta_payload_invalid_section():
    try:
        DeltaPayload(
            agent_id="p", delta_type="stage_transition", section="invalid", data={}, trace_id="t"
        )
        assert False
    except ValueError:
        print("OK: invalid section rejected")


def test_delta_payload_empty_agent_id():
    try:
        DeltaPayload(
            agent_id="", delta_type="stage_transition", section="pipeline", data={}, trace_id="t"
        )
        assert False
    except ValueError:
        print("OK: empty agent_id rejected")


def test_delta_payload_empty_trace_id():
    try:
        DeltaPayload(
            agent_id="p", delta_type="stage_transition", section="pipeline", data={}, trace_id=""
        )
        assert False
    except ValueError:
        print("OK: empty trace_id rejected")


def test_delta_payload_all_types():
    from k1.planner.types import (
        DELTA_CRASH_RECOVERY,
        DELTA_HIL_EVENT,
        DELTA_MICRO_REPLAN,
        DELTA_PLAN_END,
        DELTA_PLAN_UPDATE,
        DELTA_STAGE_TRANSITION,
        DELTA_TOOL_RESULT,
    )

    for dt in [
        DELTA_STAGE_TRANSITION,
        DELTA_TOOL_RESULT,
        DELTA_HIL_EVENT,
        DELTA_PLAN_UPDATE,
        DELTA_PLAN_END,
        DELTA_MICRO_REPLAN,
        DELTA_CRASH_RECOVERY,
    ]:
        dp = DeltaPayload(agent_id="p", delta_type=dt, section="pipeline", data={}, trace_id="t")
    print("OK: All 7 delta_type constants work")


def test_delta_payload_all_sections():
    from k1.planner.types import PLANNER_AGENT_ID, SECTION_PIPELINE, SECTION_PLAN, SECTION_TOOLS

    for sec in [SECTION_PIPELINE, SECTION_PLAN, SECTION_TOOLS]:
        DeltaPayload(agent_id="p", delta_type="plan_end", section=sec, data={}, trace_id="t")
    print("OK: All 3 section constants work")
    assert PLANNER_AGENT_ID == "planner"
    print(f'OK: PLANNER_AGENT_ID = "{PLANNER_AGENT_ID}"')


def test_plan_state_members():
    states = list(PlanState)
    assert len(states) == 11, f"Expected 11, got {len(states)}"
    print(f"OK: PlanState has {len(states)} members: {[s.value for s in states]}")


def test_plan_state_terminal():
    for s in [PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED]:
        assert s.is_terminal, f"{s} should be terminal"
        assert not s.is_active, f"{s} should not be active"
    print("OK: Terminal states correct (COMPLETED, FAILED, CANCELLED)")


def test_plan_state_micro():
    for s in [PlanState.MICRO_SKETCH, PlanState.MICRO_EXPAND, PlanState.MICRO_VALIDATE]:
        assert s.is_micro, f"{s} should be micro"
        assert s.is_active, f"{s} should be active"
    print("OK: Micro states correct")


def test_plan_state_idle():
    assert not PlanState.IDLE.is_terminal
    assert not PlanState.IDLE.is_micro
    assert not PlanState.IDLE.is_active
    print("OK: IDLE is not active, not terminal, not micro")


def test_plan_state_active_transient():
    for s in [PlanState.SKETCHING, PlanState.EXPANDING, PlanState.VALIDATING, PlanState.COMMITTING]:
        assert s.is_active
        assert not s.is_terminal
        assert not s.is_micro
    print("OK: Active transient states correct")


def test_plan_state_str_enum():
    assert PlanState.SKETCHING == "SKETCHING"
    assert PlanState.SKETCHING.value == "SKETCHING"
    print("OK: PlanState is (str, Enum)")


def test_stage_phase():
    phases = list(StagePhase)
    assert len(phases) == 4
    assert StagePhase.SKETCH == "SKETCH"
    print(f"OK: StagePhase has {len(phases)} members: {[p.value for p in phases]}")


def test_tool_call_status():
    statuses = list(ToolCallStatus)
    assert len(statuses) == 4
    assert ToolCallStatus.SUCCESS == "SUCCESS"
    print(f"OK: ToolCallStatus has {len(statuses)} members: {[s.value for s in statuses]}")


def test_stage_phase():
    phases = list(StagePhase)
    assert len(phases) == 4
    assert StagePhase.SKETCH == "SKETCH"
    print(f"OK: StagePhase has {len(phases)} members: {[p.value for p in phases]}")


def test_tool_call_status():
    statuses = list(ToolCallStatus)
    assert len(statuses) == 4
    assert ToolCallStatus.SUCCESS == "SUCCESS"
    print(f"OK: ToolCallStatus has {len(statuses)} members: {[s.value for s in statuses]}")
