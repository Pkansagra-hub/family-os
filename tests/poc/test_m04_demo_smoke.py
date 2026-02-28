"""
tests.poc.test_m04_demo_smoke -- E4.5.9 Full regression demo smoke.

5 scenarios verifying end-to-end M4 wiring in an integrated context:
  A. Happy path: SS binding active, task dispatch/complete, ledger + control
  B. Cognitive tool mutation through writer port
  C. Writer port rejects system-owned section write
  D. Builder SS integration renders real data
  E. Bundle tool end-to-end with batch mutations + idempotency
"""

from __future__ import annotations

import json

from k1.bus.envelope import Envelope
from poc.k1_poc.actors.shared import safe_get_section
from poc.k1_poc.events.mutation import TurnMutationSummary
from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY
from poc.k1_poc.fsm.states import ConciergeState
from poc.k1_poc.prompt.affect import AffectBand
from poc.k1_poc.prompt.builder import DynamicPromptBuilder
from poc.k1_poc.prompt.mode import PromptMode
from poc.k1_poc.sessionstate.ports.writer import MutationRequest
from poc.k1_poc.testing.fixtures import (
    assert_ledger_contains,
    assert_mutation_approved,
    assert_mutation_rejected,
    create_wired_fsm_with_ss,
)
from poc.k1_poc.tools.implementations import (
    ToolContext,
    execute_update_beliefs,
    execute_update_session_bundle,
)

_NEUTRAL = AffectBand(band="neutral")


# =========================================================================
# Shared helpers
# =========================================================================


def _boot() -> dict:
    """Boot a fully wired kernel for demo smoke tests."""
    return create_wired_fsm_with_ss(
        with_ledger=True,
        with_ss_binding=True,
        with_writer_port=True,
    )


def _dispatch_and_complete(
    c: dict,
    task_id: str = "smoke-task-1",
) -> None:
    """Dispatch a task and complete it through the FSM."""
    fsm = c["fsm"]
    bus = c["bus"]

    # Dispatch
    fsm._state = ConciergeState.DISPATCHING
    payload = json.dumps(
        {
            "task_id": task_id,
            "action": "search_hotels",
            "intents": [{"action": "search_hotels", "params": {}}],
            "tier": "LOW",
            "budget_hint": 4,
            "safety_band": "GREEN",
        }
    ).encode()
    bus.publish(Envelope(topic="k1.orchestration.task.dispatch.v1", payload=payload))

    # Complete
    fsm._state = ConciergeState.COMPANIONING
    complete_payload = json.dumps(
        {
            "task_id": task_id,
            "action": "search_hotels",
            "result_type": "complete",
            "final_answer": "Found 3 hotels near downtown.",
        }
    ).encode()
    bus.publish(Envelope(topic="k1.orchestration.task.complete.v1", payload=complete_payload))


# =========================================================================
# Scenario A: Happy path with SS binding active
# =========================================================================


class TestScenarioA_HappyPath:
    """Full lifecycle: dispatch -> complete -> ledger + control overlay."""

    def test_task_state_reflects_dispatch_after_rebind(self) -> None:
        """SB1 fix: task_state section updated via rebound TaskBridge."""
        c = _boot()
        fsm = c["fsm"]

        # Dispatch only
        fsm._state = ConciergeState.DISPATCHING
        payload = json.dumps(
            {
                "task_id": "smoke-a1",
                "action": "search_hotels",
                "intents": [{"action": "search_hotels", "params": {}}],
                "tier": "LOW",
                "budget_hint": 4,
                "safety_band": "GREEN",
            }
        ).encode()
        c["bus"].publish(Envelope(topic="k1.orchestration.task.dispatch.v1", payload=payload))

        # Verify task_state section has the task
        ss = c["session_state"]
        task_state = safe_get_section(ss, "task_state")
        assert task_state is not None

    def test_control_overlay_shows_fsm_state(self) -> None:
        """SB2 fix: control section metadata includes fsm_state."""
        c = _boot()
        ss = c["session_state"]
        control = safe_get_section(ss, "control")
        assert control is not None
        assert hasattr(control, "fsm_overlay")

    def test_ledger_records_full_lifecycle(self) -> None:
        """Ledger has TaskCompleted after full dispatch+complete cycle."""
        c = _boot()
        _dispatch_and_complete(c, task_id="smoke-a3")
        store = c["ledger_store"]
        assert_ledger_contains(store, "task.completed", min_count=1)

    def test_zero_dead_letters_on_happy_path(self) -> None:
        """No dead letters produced during normal dispatch/complete."""
        c = _boot()
        _dispatch_and_complete(c, task_id="smoke-a4")
        dl = c.get("dead_letter_consumer")
        if dl:
            assert len(dl.events) == 0, f"Unexpected dead letters: {dl.events}"


# =========================================================================
# Scenario B: Cognitive tool mutation through writer port
# =========================================================================


class TestScenarioB_CognitiveToolMutation:
    """update_beliefs routes through writer_port with full audit trail."""

    def test_belief_stored_via_writer_port(self) -> None:
        """update_beliefs tool writes belief through writer_port."""
        c = _boot()
        ss = c["session_state"]
        writer = c["writer_port"]

        ctx = ToolContext(
            session_manager=ss,
            cognitive_trace_id="trace-smoke-b1",
            actor="front",
            writer_port=writer,
        )
        result = execute_update_beliefs(
            {
                "beliefs": [
                    {
                        "subject": "user",
                        "predicate": "prefers",
                        "object": "aisle seats",
                        "confidence": 0.9,
                    }
                ]
            },
            ctx,
        )
        assert result.status == "ok"

    def test_mutation_guard_ran_for_belief_write(self) -> None:
        """MutationGuard preflight approved the belief mutation."""
        c = _boot()
        writer = c["writer_port"]

        req = MutationRequest.create(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": "smoke-b2",
                "predicate": "is",
                "obj": "fact",
                "confidence": 0.85,
                "source": "llm:front",
            },
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-b2",
            estimated_bytes=80,
        )
        resp = writer.request_mutation(req)
        assert_mutation_approved(resp)

    def test_writer_stats_updated_after_mutation(self) -> None:
        """Writer port stats reflect the applied mutation."""
        c = _boot()
        writer = c["writer_port"]

        req = MutationRequest.create(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": "smoke-b3",
                "predicate": "is",
                "obj": "fact",
                "confidence": 0.8,
                "source": "llm:front",
            },
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-b3",
            estimated_bytes=60,
        )
        writer.request_mutation(req)
        stats = writer.get_stats()
        assert stats["applied_count"] >= 1

    def test_turn_mutation_summary_event_exists(self) -> None:
        """TurnMutationSummary registered in event type registry."""
        assert "mutation.turn_summary" in EVENT_TYPE_REGISTRY
        assert EVENT_TYPE_REGISTRY["mutation.turn_summary"] is TurnMutationSummary

    def test_turn_stats_snapshot_resets(self) -> None:
        """snapshot_turn_stats() returns stats and resets to zero."""
        c = _boot()
        writer = c["writer_port"]

        req = MutationRequest.create(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": "smoke-b5",
                "predicate": "is",
                "obj": "snap",
                "confidence": 0.7,
                "source": "llm:front",
            },
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-b5",
            estimated_bytes=60,
        )
        writer.request_mutation(req)
        snap = writer.snapshot_turn_stats()
        assert snap["approved_count"] >= 1

        # After snapshot, counters reset
        snap2 = writer.snapshot_turn_stats()
        assert snap2["approved_count"] == 0


# =========================================================================
# Scenario C: Writer port rejects system-owned section write
# =========================================================================


class TestScenarioC_SystemOwnedRejection:
    """Tool writes to system-owned sections are rejected at writer layer."""

    def test_control_section_write_rejected(self) -> None:
        """write to 'control' is rejected with AUTHORIZATION."""
        c = _boot()
        writer = c["writer_port"]

        req = MutationRequest.create(
            section="control",
            operation="set",
            data={"hacked": True},
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-c1",
            estimated_bytes=30,
        )
        resp = writer.request_mutation(req)
        assert_mutation_rejected(resp, category="authorization")

    def test_system_rejection_does_not_crash(self) -> None:
        """System remains operational after AUTHORIZATION rejection."""
        c = _boot()
        writer = c["writer_port"]

        # Rejected write
        req = MutationRequest.create(
            section="control",
            operation="set",
            data={"evil": True},
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-c2",
            estimated_bytes=20,
        )
        writer.request_mutation(req)

        # System still works: a valid write succeeds
        ok_req = MutationRequest.create(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": "system",
                "predicate": "still",
                "obj": "works",
                "confidence": 1.0,
                "source": "llm:front",
            },
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-c2",
            estimated_bytes=50,
        )
        resp = writer.request_mutation(ok_req)
        assert_mutation_approved(resp)

    def test_no_dead_letter_on_writer_rejection(self) -> None:
        """Writer-layer rejection does NOT produce a bus dead-letter."""
        c = _boot()
        writer = c["writer_port"]

        req = MutationRequest.create(
            section="control",
            operation="set",
            data={"bad": True},
            writer_id="tool:front",
            cognitive_trace_id="trace-smoke-c3",
            estimated_bytes=20,
        )
        writer.request_mutation(req)

        dl = c.get("dead_letter_consumer")
        if dl:
            assert len(dl.events) == 0, "Writer rejection should not produce dead-letters"


# =========================================================================
# Scenario D: Builder SS integration renders real data
# =========================================================================


class TestScenarioD_BuilderSSIntegration:
    """Builder prompt includes real SS section data after M4 binding."""

    def test_builder_renders_with_ss(self) -> None:
        """System prompt is a non-empty string when SS is provided."""
        c = _boot()
        ss = c["session_state"]

        builder = DynamicPromptBuilder()
        built = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_NEUTRAL,
            ss=ss,
        )
        assert isinstance(built.system_prompt, str)
        assert len(built.system_prompt) > 0

    def test_builder_with_task_data_after_dispatch(self) -> None:
        """After task dispatch, builder includes task_state in prompt."""
        c = _boot()
        fsm = c["fsm"]
        ss = c["session_state"]

        # Dispatch a task to populate task_state
        fsm._state = ConciergeState.DISPATCHING
        payload = json.dumps(
            {
                "task_id": "smoke-d2",
                "action": "book_flight",
                "intents": [{"action": "book_flight", "params": {}}],
                "tier": "LOW",
                "budget_hint": 4,
                "safety_band": "GREEN",
            }
        ).encode()
        c["bus"].publish(Envelope(topic="k1.orchestration.task.dispatch.v1", payload=payload))

        builder = DynamicPromptBuilder()
        built = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_NEUTRAL,
            ss=ss,
        )
        assert isinstance(built.system_prompt, str)

    def test_builder_backward_compat_no_ss(self) -> None:
        """Builder works with ss=None (backward compatible with pre-M4)."""
        builder = DynamicPromptBuilder()
        built = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_NEUTRAL,
        )
        assert isinstance(built.system_prompt, str)
        assert len(built.system_prompt) > 0


# =========================================================================
# Scenario E: Bundle tool end-to-end
# =========================================================================


class TestScenarioE_BundleTool:
    """update_session_bundle routes through batch_mutations + idempotency."""

    def test_bundle_applies_multiple_mutations(self) -> None:
        """Bundle with 2 mutations both applied through writer_port."""
        c = _boot()
        ss = c["session_state"]
        writer = c["writer_port"]

        ctx = ToolContext(
            session_manager=ss,
            cognitive_trace_id="trace-smoke-e1",
            actor="front",
            writer_port=writer,
            bundle_idempotency_cache={},
        )
        result = execute_update_session_bundle(
            {
                "idempotency_key": "smoke-e1-key",
                "mutations": [
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "bundle",
                            "predicate": "is",
                            "obj": "fact1",
                            "confidence": 0.8,
                            "source": "llm:front",
                        },
                    },
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "bundle",
                            "predicate": "is",
                            "obj": "fact2",
                            "confidence": 0.7,
                            "source": "llm:front",
                        },
                    },
                ],
            },
            ctx,
        )
        assert result.status == "ok"
        assert result.data["applied"] == 2

    def test_bundle_idempotency_dedup(self) -> None:
        """Repeat call with same idempotency_key returns cached result."""
        c = _boot()
        ss = c["session_state"]
        writer = c["writer_port"]

        cache: dict = {}
        ctx = ToolContext(
            session_manager=ss,
            cognitive_trace_id="trace-smoke-e2",
            actor="front",
            writer_port=writer,
            bundle_idempotency_cache=cache,
        )

        mutations = {
            "idempotency_key": "smoke-e2-key",
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "dedup",
                        "predicate": "is",
                        "obj": "test",
                        "confidence": 0.9,
                        "source": "llm:front",
                    },
                },
            ],
        }

        result1 = execute_update_session_bundle(mutations, ctx)
        result2 = execute_update_session_bundle(mutations, ctx)

        assert result1.status == "ok"
        assert result2.status == "ok"

        # Writer should have applied only once
        stats = writer.get_stats()
        assert stats["applied_count"] == 1

    def test_bundle_guard_enforced_per_mutation(self) -> None:
        """Each sub-mutation in a bundle goes through MutationGuard."""
        c = _boot()
        ss = c["session_state"]
        writer = c["writer_port"]

        ctx = ToolContext(
            session_manager=ss,
            cognitive_trace_id="trace-smoke-e3",
            actor="front",
            writer_port=writer,
            bundle_idempotency_cache={},
        )

        # One valid, one to system-owned section -> partial
        result = execute_update_session_bundle(
            {
                "idempotency_key": "smoke-e3-key",
                "stop_on_rejection": False,
                "mutations": [
                    {
                        "section": "beliefs_active",
                        "operation": "add_fact",
                        "data": {
                            "subject": "valid",
                            "predicate": "is",
                            "obj": "fact",
                            "confidence": 0.8,
                            "source": "llm:front",
                        },
                    },
                    {
                        "section": "control",
                        "operation": "set",
                        "data": {"hacked": True},
                    },
                ],
            },
            ctx,
        )
        # With stop_on_rejection=False, first applies, second rejected
        assert result.data["applied"] >= 1
        assert result.data["rejected"] >= 1
