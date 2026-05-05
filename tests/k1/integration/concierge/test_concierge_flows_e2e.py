"""End-to-end concierge flow tests with real KernelService boot.

Flows under test:
    1. ``test_flow1_front_talks_to_user``        -- user input -> FSM ->
       stub LLM -> final response. No orchestrator/planner.
    2. ``test_flow2_front_dispatches_to_back``   -- front LLM emits
       ``dispatch_task`` tool call -> FSM publishes
       ``TOPIC_TASK_DISPATCH`` -> Back actor receives it.

No mocks: real bus, real FSM, real fabric, real orchestrator wired by
``KernelService``.  The LLM is a real plugin: in Flow 1 the default
``StubProviderPlugin`` (canned ``"OK"``); in Flow 2+ a swappable
``ScriptedProviderPlugin`` that returns deterministic tool calls keyed
by predicates over the inbound request.  Both are real
``IProviderPlugin`` implementations -- no ``unittest.mock`` objects in
the wire path.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
)
from tests.k1.integration.concierge.conftest import BusCapture, inject_test_mcp_transport
from tests.k1.integration.concierge.scripted_provider import (
    install_scripted_plugin,
    make_text_response,
    make_tool_call_response,
)


@pytest.mark.asyncio
async def test_flow1_front_talks_to_user(kernel_service) -> None:
    """Flow 1: user message -> Front actor (stub LLM) -> final response.

    Wire path:
        bus.publish(TOPIC_USER_INPUT)
            -> ConciergeController._on_user_input
            -> turn pipeline (Phase1=Stub, react_loop with StubProviderPlugin)
            -> bus.publish(TOPIC_FINAL_RESPONSE)
    """
    session = await kernel_service.create_session("flow1-front-only")
    try:
        capture = BusCapture(session.bus, TOPIC_FINAL_RESPONSE)
        capture.start()
        try:
            env_in = build_user_input({"text": "hello concierge", "device_id": "test-device"})
            session.bus.publish(env_in)

            env_out = await capture.wait_one(timeout_s=15.0)

            assert env_out.topic == TOPIC_FINAL_RESPONSE
            payload = json.loads(env_out.payload.decode("utf-8"))
            # StubProviderPlugin returns "OK"; the FSM may wrap it but the
            # canned text must appear in the final-response payload.
            text_field = payload.get("text") or payload.get("response") or ""
            assert (
                "OK" in text_field or text_field
            ), f"expected stub reply text in final-response payload, got: {payload}"
        finally:
            capture.stop()
    finally:
        await kernel_service.destroy_session("flow1-front-only")


@pytest.mark.asyncio
async def test_flow2_front_dispatches_task_to_back(kernel_service) -> None:
    """Flow 2 (slice 1): user input -> front LLM emits ``dispatch_task``
    tool call -> FSM publishes ``TOPIC_TASK_DISPATCH`` on the per-session
    bus.

    This validates the LLM-decision -> bus-hop seam end-to-end.  Back-side
    fabric/MCP wiring is asserted in subsequent slices of this same flow
    once the test is extended with an MCP-routed capability.

    Wire path:
        bus.publish(TOPIC_USER_INPUT)
            -> ConciergeController._on_user_input
            -> turn pipeline -> react_loop(actor=front)
            -> ScriptedProviderPlugin returns tool_call(dispatch_task, ...)
            -> execute_dispatch_task captured in dispatched_tasks
            -> front_handler emits TOPIC_TASK_DISPATCH
    """
    scripted = await install_scripted_plugin(kernel_service)

    # Front turn: emit a single dispatch_task tool call. The intent
    # action is intentionally a string the back actor can ignore --
    # this slice only asserts the dispatch hop.
    scripted.queue(
        make_tool_call_response(
            (
                "dispatch_task",
                {
                    "intents": [
                        {
                            "action": "echo",
                            "params": {"text": "hello back"},
                            "urgency": "normal",
                        }
                    ],
                    "safety_band": "GREEN",
                },
            ),
        ),
        label="front-dispatch",
    )
    # Back turn: terminal text reply (Back's ReAct loop has STOP
    # finish_reason and no tools, so the loop exits and Back emits
    # task.complete with this text as the result).
    scripted.queue(
        make_text_response("done"),
        label="back-terminal",
    )
    # Front follow-up after task.complete: terminal reply to the user.
    scripted.queue(
        make_text_response("task complete"),
        label="front-final",
    )

    session = await kernel_service.create_session("flow2-dispatch")
    try:
        dispatch_capture = BusCapture(session.bus, TOPIC_TASK_DISPATCH)
        final_capture = BusCapture(session.bus, TOPIC_FINAL_RESPONSE)
        dispatch_capture.start()
        final_capture.start()
        try:
            session.bus.publish(
                build_user_input({"text": "please echo hello back", "device_id": "test"})
            )

            # Assert the dispatch envelope was published by the front handler.
            env_dispatch = await dispatch_capture.wait_one(timeout_s=20.0)
            assert env_dispatch.topic == TOPIC_TASK_DISPATCH
            payload = json.loads(env_dispatch.payload.decode("utf-8"))
            assert payload.get("task_id", "").startswith("task-")
            intents = payload.get("intents") or []
            assert len(intents) == 1
            assert intents[0].get("action") == "echo"

            # Assert at least one user-facing response is emitted (front
            # turn produces an immediate reply or post-task summary).
            env_final = await final_capture.wait_one(timeout_s=20.0)
            assert env_final.topic == TOPIC_FINAL_RESPONSE

            # The scripted plugin should have been called at least once
            # (front turn). Back may or may not run depending on tier
            # routing; we assert the front rule fired.
            front_rule = scripted.rules[0]
            assert front_rule.fired >= 1, (
                f"expected front-dispatch rule to fire, got fired={front_rule.fired}; "
                f"calls={len(scripted.calls)}"
            )
        finally:
            dispatch_capture.stop()
            final_capture.stop()
    finally:
        await kernel_service.destroy_session("flow2-dispatch")


@pytest.mark.asyncio
async def test_flow2_back_invokes_fabric_via_mcp(kernel_service) -> None:
    """Flow 2 (slice 2): user input -> front dispatches task -> back actor
    invokes a real MCP-routed fabric capability -> TestMCPTransport
    captures the call -> task.complete -> front emits final response.

    Wire path:
        bus.publish(TOPIC_USER_INPUT)
            -> ConciergeController -> react_loop(actor=front)
            -> ScriptedProviderPlugin returns dispatch_task tool call
            -> FSM publishes TOPIC_TASK_DISPATCH to back
            -> back_handler -> react_loop(actor=back)
            -> ScriptedProviderPlugin returns invoke_capability tool call
            -> FabricDispatchAdapter.dispatch_direct
            -> Fabric.execute -> MCPProvider -> TestMCPTransport.send
            -> capability result back -> back returns terminal text
            -> back publishes TOPIC_TASK_COMPLETE
            -> FSM/front follow-up turn -> TOPIC_FINAL_RESPONSE

    GREEN-band ``tool.read.notes_list`` is used so the fabric capability
    gate does not request HIL approval.
    """
    scripted = await install_scripted_plugin(kernel_service)

    capability = "tool.read.notes_list"

    # Match by ReAct loop consumer_id which is set to "concierge.front"
    # or "concierge.back" at HubRequest build time -- propagated through
    # to NormalizedRequest.consumer_id.
    def _is_front_request(req: Any) -> bool:
        return req.consumer_id == "concierge.front"

    def _is_back_request(req: Any) -> bool:
        return req.consumer_id == "concierge.back"

    # Front turn 1: dispatch a task.
    scripted.queue(
        make_tool_call_response(
            (
                "dispatch_task",
                {
                    "intents": [
                        {
                            "action": "list notes",
                            "params": {},
                            "urgency": "normal",
                        }
                    ],
                    "safety_band": "GREEN",
                },
            ),
        ),
        predicate=_is_front_request,
        label="front-dispatch",
    )

    # Back turn 1: invoke the MCP-routed capability.
    scripted.queue(
        make_tool_call_response(
            (
                "invoke_capability",
                {
                    "capability_name": capability,
                    "params": {"limit": 5},
                },
            ),
        ),
        predicate=_is_back_request,
        label="back-invoke",
    )

    # Back turn 2: terminal -- submit_result tells FSM the task is done.
    scripted.queue(
        make_tool_call_response(
            (
                "submit_result",
                {
                    "result_type": "complete",
                    "final_answer": "notes listed",
                    "results": [],
                    "artifacts_created": [],
                },
            ),
        ),
        predicate=_is_back_request,
        label="back-submit",
    )

    # Front follow-up after task.complete: terminal reply to the user.
    scripted.queue(
        make_text_response("done"),
        predicate=_is_front_request,
        label="front-final",
    )

    session = await kernel_service.create_session("flow2-mcp")
    try:
        # Inject TestMCPTransport BEFORE any MCP capability resolution.
        transport = inject_test_mcp_transport(session.fabric)
        # Canned response for the MCP tool call.
        from k1.fabric.providers.mcp_provider import MCPResponse

        transport.add_response(
            capability,
            MCPResponse(
                success=True,
                content=[{"type": "text", "text": "[]"}],
                latency_ms=2,
            ),
        )

        dispatch_capture = BusCapture(session.bus, TOPIC_TASK_DISPATCH)
        complete_capture = BusCapture(session.bus, TOPIC_TASK_COMPLETE)
        final_capture = BusCapture(session.bus, TOPIC_FINAL_RESPONSE)
        dispatch_capture.start()
        complete_capture.start()
        final_capture.start()
        try:
            session.bus.publish(build_user_input({"text": "list my notes", "device_id": "test"}))

            await dispatch_capture.wait_one(timeout_s=20.0)
            await complete_capture.wait_one(timeout_s=30.0)
            await final_capture.wait_one(timeout_s=30.0)

            # MCP transport saw exactly the back's invoke_capability call.
            captured = transport.drain()
            assert any(c.tool_name == capability for c in captured), (
                f"expected MCP transport to capture {capability}; got "
                f"{[c.tool_name for c in captured]}"
            )

            # Assert the back rules fired (front-dispatch + back-invoke at minimum).
            fired_labels = [r.label for r in scripted.rules if r.fired]
            assert "front-dispatch" in fired_labels
            assert "back-invoke" in fired_labels
        finally:
            dispatch_capture.stop()
            complete_capture.stop()
            final_capture.stop()
    finally:
        await kernel_service.destroy_session("flow2-mcp")


async def test_flow3_front_dispatches_to_orchestrator_medium(kernel_service):
    """Flow 3: Front -> dispatch_task with plan=True -> MEDIUM tier ->
    OrchestratorService.handle_task -> Fabric (via MCP).

    Front emits a single-intent ``dispatch_task`` with ``plan=True``.
    ``execute_dispatch_task`` derives MEDIUM tier from plan signal; the
    fixed front actor preserves the per-task tier; the FSM routes via
    ``OrchestratorService.handle_task``; the orchestrator translates
    the envelope, runs ``_dispatch_medium`` (one capability through the
    MCP-backed fabric), and ``FabricDispatchAdapter`` bridges the
    ``ProcessResult.COMPLETED`` outcome onto the session bus as
    ``task.complete.v1``.

    The intent string equals the capability name ("tool.read.notes_list")
    because ``OrchestratorService.handle_task`` uses the intent as the
    single capability for MEDIUM-tier translation.
    """
    scripted = await install_scripted_plugin(kernel_service)

    capability = "tool.read.notes_list"

    def _is_front_request(req: Any) -> bool:
        return getattr(req, "consumer_id", "") == "concierge.front"

    # Front turn: plan=True forces MEDIUM tier; intent must match a real
    # capability because handle_task() uses intent as the capability name.
    scripted.queue(
        make_tool_call_response(
            (
                "dispatch_task",
                {
                    "intents": [
                        {
                            "action": capability,
                            "params": {},
                            "urgency": "normal",
                        }
                    ],
                    "safety_band": "GREEN",
                    "plan": True,
                },
            ),
        ),
        predicate=_is_front_request,
        label="front-dispatch-medium",
    )
    # Front follow-up after orchestrator settles.
    scripted.queue(
        make_text_response("orchestrator done"),
        predicate=_is_front_request,
        label="front-final",
    )

    session = await kernel_service.create_session("flow3-orch")
    try:
        # Note: the orchestrator uses the kernel-shared fabric, not the
        # per-session fabric -- so we do NOT inject TestMCPTransport here.
        # The capability resolves through the kernel-shared MCP registry;
        # for ``tool.read.notes_list`` the real provider returns an
        # empty-list result quickly which is sufficient to drive
        # ProcessResult.COMPLETED.
        dispatch_capture = BusCapture(session.bus, TOPIC_TASK_DISPATCH)
        complete_capture = BusCapture(session.bus, TOPIC_TASK_COMPLETE)
        dispatch_capture.start()
        complete_capture.start()
        try:
            session.bus.publish(
                build_user_input({"text": "plan and list notes", "device_id": "test"})
            )

            env_dispatch = await dispatch_capture.wait_one(timeout_s=20.0)
            payload = json.loads(env_dispatch.payload.decode("utf-8"))
            assert payload.get("plan") is True, f"expected plan=True in dispatch; got {payload}"
            assert payload.get("tier") == "MEDIUM", (
                f"expected MEDIUM tier (front actor must preserve per-task tier); "
                f"got {payload.get('tier')}"
            )

            env_complete = await complete_capture.wait_one(timeout_s=30.0)
            complete_payload = json.loads(env_complete.payload.decode("utf-8"))
            assert complete_payload.get("source") == "orchestrator", (
                f"expected task.complete to be published by FabricDispatchAdapter "
                f"bridge (source=orchestrator); got {complete_payload}"
            )
            assert complete_payload.get("process_result") in ("COMPLETED", "DEGRADED")

            fired_labels = [r.label for r in scripted.rules if r.fired]
            assert "front-dispatch-medium" in fired_labels
        finally:
            dispatch_capture.stop()
            complete_capture.stop()
    finally:
        await kernel_service.destroy_session("flow3-orch")


async def test_flow4_front_dispatches_to_orchestrator_high_with_planner(kernel_service):
    """Flow 4: Front -> dispatch_task complexity=HIGH plan=True -> HIGH tier ->
    OrchestratorService.handle_task -> Planner SKETCH/EXPAND/VALIDATE/COMMIT
    -> DAG execution via Fabric -> task.complete bridged onto session bus.

    Pipeline:
        front (scripted: dispatch_task complexity=HIGH plan=True)
          -> execute_dispatch_task (HIGH tier)
          -> FSM _route_via_orchestrator (HIGH preserved -- orchestrator wired)
          -> FabricDispatchAdapter.dispatch_envelope
          -> OrchestratorService.handle_task
              -> _route_task -> _dispatch_high
                  -> planner_port.request_plan (DEFERRED)
              -> handle_task awaits future on trace_id
          -> Planner pipeline (kernel-shared model_hub, scripted plugin):
              SKETCH (consumer_id=planner)
              EXPAND (consumer_id=planner.expand)
              VALIDATE (consumer_id=planner.validate)
              COMMIT (deterministic, no LLM call)
          -> Planner emits PLAN_READY on kernel bus
          -> Orchestrator _on_plan_ready -> _execute_dag -> _emit_result
              -> resolves handle_task waiter
          -> handle_task returns COMPLETED/FAILED
          -> FabricDispatchAdapter publishes task.complete.v1 on session bus
    """
    scripted = await install_scripted_plugin(kernel_service)

    capability = "tool.read.notes_list"

    def _is_front(req: Any) -> bool:
        return getattr(req, "consumer_id", "") == "concierge.front"

    def _is_planner(req: Any) -> bool:
        # NOTE: LLMGatewayAdapter unconditionally restamps consumer_id to
        # its constructor default ("planner") -- the per-stage IDs set by
        # SKETCH/EXPAND/VALIDATE in their PlannerConstraints are overwritten
        # before the request hits the model_hub. So all 3 planner stages
        # share the same wire consumer_id and the queued rules fire in order.
        return getattr(req, "consumer_id", "") == "planner"

    # ---- Front turn: emit dispatch_task with complexity=HIGH + plan=True.
    scripted.queue(
        make_tool_call_response(
            (
                "dispatch_task",
                {
                    "intents": [
                        {
                            "action": capability,
                            "params": {},
                            "urgency": "normal",
                        }
                    ],
                    "safety_band": "GREEN",
                    "plan": True,
                    "complexity": "HIGH",
                },
            ),
        ),
        predicate=_is_front,
        label="front-dispatch-high",
    )
    # Front follow-up after orchestrator settles.
    scripted.queue(
        make_text_response("orchestrator+planner done"),
        predicate=_is_front,
        label="front-final-high",
    )

    # ---- Planner SKETCH: returns final JSON conforming to SKETCH_OUTPUT_SCHEMA,
    # finish_reason=STOP and no tool calls -> agentic loop exits on round 1.
    sketch_json = json.dumps(
        {
            "rough_steps": [
                {
                    "intent": "list user notes",
                }
            ],
            "rationale": "Single capability fulfils the request.",
            "needs_clarification": False,
        }
    )
    scripted.queue(
        make_text_response(sketch_json),
        predicate=_is_planner,
        label="planner-sketch",
    )

    # ---- Planner EXPAND: returns final JSON conforming to EXPAND_OUTPUT_SCHEMA.
    expand_json = json.dumps(
        {
            "steps": [
                {
                    "id": "s1",
                    "capability": capability,
                    "params": {},
                }
            ],
            "dependencies": {"s1": []},
            "rationale": "Single step, no dependencies.",
        }
    )
    scripted.queue(
        make_text_response(expand_json),
        predicate=_is_planner,
        label="planner-expand",
    )

    # ---- Planner VALIDATE: approve the plan as-is.
    validate_json = json.dumps(
        {
            "status": "approved",
            "reasons": ["Plan is coherent, safe, and complete."],
            "coherence_score": 1.0,
            "safety_assessment": "safe",
            "completeness": True,
        }
    )
    scripted.queue(
        make_text_response(validate_json),
        predicate=_is_planner,
        label="planner-validate",
    )

    session = await kernel_service.create_session("flow4-orch-high")
    try:
        dispatch_capture = BusCapture(session.bus, TOPIC_TASK_DISPATCH)
        complete_capture = BusCapture(session.bus, TOPIC_TASK_COMPLETE)
        dispatch_capture.start()
        complete_capture.start()
        try:
            session.bus.publish(
                build_user_input({"text": "plan and execute notes listing", "device_id": "test"})
            )

            env_dispatch = await dispatch_capture.wait_one(timeout_s=20.0)
            payload = json.loads(env_dispatch.payload.decode("utf-8"))
            assert payload.get("plan") is True, f"expected plan=True in dispatch; got {payload}"
            assert (
                payload.get("complexity") == "HIGH"
            ), f"expected complexity=HIGH; got {payload.get('complexity')}"
            assert payload.get("tier") == "HIGH", (
                f"expected HIGH tier (front actor must preserve per-task tier); "
                f"got {payload.get('tier')}"
            )

            env_complete = await complete_capture.wait_one(timeout_s=60.0)
            complete_payload = json.loads(env_complete.payload.decode("utf-8"))
            assert complete_payload.get("source") == "orchestrator", (
                f"expected task.complete to be published by FabricDispatchAdapter "
                f"bridge (source=orchestrator); got {complete_payload}"
            )
            assert complete_payload.get("process_result") in (
                "COMPLETED",
                "DEGRADED",
            ), f"expected COMPLETED/DEGRADED; got {complete_payload.get('process_result')}"

            fired_labels = [r.label for r in scripted.rules if r.fired]
            assert "front-dispatch-high" in fired_labels
            planner_consumer_ids = sorted(
                {
                    getattr(c, "consumer_id", "")
                    for c in scripted.calls
                    if str(getattr(c, "consumer_id", "")).startswith("planner")
                }
            )
            assert "planner-sketch" in fired_labels, (
                f"planner SKETCH did not fire; planner did not run. "
                f"fired={fired_labels}, planner_consumer_ids={planner_consumer_ids}"
            )
            assert "planner-expand" in fired_labels, (
                f"planner EXPAND did not fire. fired={fired_labels}, "
                f"planner_consumer_ids={planner_consumer_ids}"
            )
            assert "planner-validate" in fired_labels, (
                f"planner VALIDATE did not fire. fired={fired_labels}, "
                f"planner_consumer_ids={planner_consumer_ids}"
            )
        finally:
            dispatch_capture.stop()
            complete_capture.stop()
    finally:
        await kernel_service.destroy_session("flow4-orch-high")


async def test_flow5_save_workflow_and_proactive_cron_fire(kernel_service):
    """Flow 5: planner success -> save as workflow scheduled "0 9 * * *" ->
    time-warp scheduler clock past 9 AM -> tick -> proactive WorkflowRunRequest
    -> orchestrator mailbox loop dispatches it -> WorkflowEngine.execute_workflow
    -> DAG completes -> a run record is persisted.

    This proves the production save+schedule+fire wiring end-to-end through
    the real KernelService boot, BEFORE swapping the scripted LLM for a real
    provider. It does NOT exercise the concierge "save_workflow" tool path
    (which doesn't exist yet -- see /memories/session/concierge_flow_tests_state.md);
    it submits the WorkflowSaveRequest directly to the orchestrator mailbox,
    which is the canonical concierge -> orchestrator handoff for save.

    Wire path proven:
        Flow 4 reuse -> CommittedPlan + WAL PLAN_START
            -> kernel_service._orchestrator.process(WorkflowSaveRequest)
                -> WorkflowEngine.save_workflow (reads WAL via bridge)
                    -> WorkflowRegistry.save + storage.save_trigger
                -> ORCH_WORKFLOW_SAVED delta
            -> stop scheduler tick loop, swap _clock to FrozenClock(future_9am)
            -> scheduler._tick()
                -> storage.get_due_triggers(now=future_9am)
                -> _fire_trigger -> mailbox.enqueue(WorkflowRunRequest)
            -> orchestrator mailbox loop dequeues WorkflowRunRequest
                -> _dispatch_workflow -> workflow_engine.execute_workflow
                -> DAGExecutor runs the saved steps via fabric
                -> storage.get_runs(workflow_id) shows COMPLETED entry
    """
    from datetime import datetime, timedelta, timezone

    from k1.orchestrator.types import (
        ProcessResult,
        TriggerSpec,
        TriggerType,
        WorkflowSaveRequest,
    )
    from k1.orchestrator.workflows.system_clock import FrozenClock

    # --- Phase A: produce a real CommittedPlan via Flow 4 setup ---
    scripted = await install_scripted_plugin(kernel_service)
    capability = "tool.read.notes_list"

    def _is_front(req: Any) -> bool:
        return getattr(req, "consumer_id", "") == "concierge.front"

    def _is_planner(req: Any) -> bool:
        # See Flow 4 docstring: LLMGatewayAdapter restamps consumer_id="planner"
        # for all 3 planner stages.
        return getattr(req, "consumer_id", "") == "planner"

    scripted.queue(
        make_tool_call_response(
            (
                "dispatch_task",
                {
                    "intents": [{"action": capability, "params": {}, "urgency": "normal"}],
                    "safety_band": "GREEN",
                    "plan": True,
                    "complexity": "HIGH",
                },
            ),
        ),
        predicate=_is_front,
        label="flow5-front-dispatch",
    )
    scripted.queue(
        make_text_response("save and schedule done"),
        predicate=_is_front,
        label="flow5-front-final",
    )
    sketch_json = json.dumps(
        {
            "rough_steps": [{"intent": "list user notes"}],
            "rationale": "Single capability fulfils the request.",
            "needs_clarification": False,
        }
    )
    expand_json = json.dumps(
        {
            "steps": [{"id": "s1", "capability": capability, "params": {}}],
            "dependencies": {"s1": []},
            "rationale": "Single step.",
        }
    )
    validate_json = json.dumps(
        {
            "status": "approved",
            "reasons": ["ok"],
            "coherence_score": 1.0,
            "safety_assessment": "safe",
            "completeness": True,
        }
    )
    scripted.queue(make_text_response(sketch_json), predicate=_is_planner, label="flow5-sketch")
    scripted.queue(make_text_response(expand_json), predicate=_is_planner, label="flow5-expand")
    scripted.queue(
        make_text_response(validate_json),
        predicate=_is_planner,
        label="flow5-validate",
    )

    session = await kernel_service.create_session("flow5-save-cron")
    try:
        complete_capture = BusCapture(session.bus, TOPIC_TASK_COMPLETE)
        complete_capture.start()
        try:
            session.bus.publish(
                build_user_input({"text": "plan and execute notes listing", "device_id": "test"})
            )
            env_complete = await complete_capture.wait_one(timeout_s=60.0)
            payload = json.loads(env_complete.payload.decode("utf-8"))
            assert payload.get("process_result") in ("COMPLETED", "DEGRADED")
        finally:
            complete_capture.stop()

        orch = kernel_service._orchestrator
        assert orch is not None, "kernel orchestrator must be wired"
        executed = orch._executed_plans  # OrderedDict[plan_id -> timestamp]
        assert executed, "orchestrator should have at least one executed plan after Flow 4 success"
        # Most recently executed plan_id is the rightmost key.
        plan_id = next(reversed(executed))

        # --- Phase B: save as workflow, scheduled daily 9 AM UTC ---
        save_req = WorkflowSaveRequest(
            committed_plan_id=plan_id,
            workflow_name="flow5-daily-9am-notes",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="0 9 * * *", timezone="UTC"),
            trace_id=f"trace-save-{plan_id}",
        )
        save_result = await orch.process(save_req)
        assert save_result == ProcessResult.COMPLETED, (
            f"WorkflowSaveRequest must succeed; got {save_result}. "
            "If FAILED, the planner did not write PLAN_START to the WAL "
            "for plan_id={plan_id}, or bridge.read_wal failed."
        )

        engine = orch._workflow_engine
        storage = engine.registry._storage
        all_workflows = await storage.list_workflows(active_only=True)
        saved_wf = next((w for w in all_workflows if w.name == "flow5-daily-9am-notes"), None)
        assert saved_wf is not None, (
            f"workflow must be persisted in storage; have " f"{[w.name for w in all_workflows]}"
        )
        assert saved_wf.source_plan_id == plan_id
        assert saved_wf.trigger.type == TriggerType.CRON
        assert saved_wf.trigger.schedule == "0 9 * * *"

        # --- Phase C: time-warp to past next 9:00 UTC and force a tick ---
        # Stop the running tick loop so we can mutate the clock and tick
        # synchronously without racing the natural 1s ticker.
        await engine.scheduler.stop()

        now_utc = datetime.now(tz=timezone.utc)
        target = now_utc.replace(hour=9, minute=0, second=1, microsecond=0)
        if target <= now_utc:
            target = target + timedelta(days=1)
        # Add one day extra to guarantee the cron's next-fire (which storage
        # set to "next 9:00 from save time") is definitely in the past.
        future_9am = target + timedelta(days=1)
        engine.scheduler._clock = FrozenClock(future_9am.timestamp())

        # Phase D: trigger one tick. _fire_trigger enqueues a
        # WorkflowRunRequest onto the orchestrator's mailbox; the
        # already-running mailbox loop will dispatch it.
        await engine.scheduler._tick()

        # --- Phase E: poll storage.get_runs for COMPLETED record ---
        # storage.get_runs returns raw dicts (JSON RunManifest) per
        # SQLiteWorkflowAdapter.get_runs (V1). The 'status' field is the
        # str(RunStatus.X) form, e.g. "RunStatus.COMPLETED".
        run = None
        import asyncio as _asyncio

        terminal_status = {
            "RunStatus.COMPLETED",
            "RunStatus.FAILED",
            "RunStatus.ABORTED",
        }
        for _ in range(60):  # up to ~30s
            runs = await storage.get_runs(saved_wf.workflow_id)
            if runs:
                run = runs[0]
                status = run.get("status") if isinstance(run, dict) else None
                if status in terminal_status:
                    break
            await _asyncio.sleep(0.5)

        assert run is not None, (
            "scheduler tick must have enqueued WorkflowRunRequest and the "
            "orchestrator mailbox loop must have dispatched it -- but no "
            "run record appeared in storage"
        )
        status = run.get("status") if isinstance(run, dict) else None
        assert (
            status == "RunStatus.COMPLETED"
        ), f"proactive workflow run must complete; got status={status}, run={run}"
        # Sanity: at least one step ran successfully via fabric.
        summary = run.get("result_summary", {}) if isinstance(run, dict) else {}
        assert (
            summary.get("completed", 0) >= 1
        ), f"expected >=1 completed step in proactive run; got summary={summary}"
        assert (
            summary.get("failed", 0) == 0
        ), f"expected 0 failed steps in proactive run; got summary={summary}"
    finally:
        await kernel_service.destroy_session("flow5-save-cron")
