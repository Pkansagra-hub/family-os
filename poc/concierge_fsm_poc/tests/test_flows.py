"""TEST-003: Flow Coverage Tests -- 20 flows from concierge_fsm_flows.md.

Each test drives the FSM through a complete flow path, verifying full state
path (not just start/end).  Uses real FSMController + MockPhase1Classifier.
No LLM, no async -- pure FSM transition verification.

Aligned to ``CONCIERGE_FSM_POC_PLAN.md`` Epic 5.3 and Appendix B.
"""

from __future__ import annotations

import pytest

from poc.concierge_fsm_poc.fsm.controller import (
    Action,
    Event,
    FSMController,
    InvalidTransitionError,
    State,
)
from poc.concierge_fsm_poc.fsm.phase1_mock import ClassifierError, MockPhase1Classifier


@pytest.fixture()
def fsm() -> FSMController:
    return FSMController()


@pytest.fixture()
def classifier() -> MockPhase1Classifier:
    return MockPhase1Classifier()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_path(fsm: FSMController, expected_states: list[State]) -> None:
    """Assert the FSM visited the expected state sequence (from -> to in history)."""
    visited = [fsm.history[0][0]]  # initial 'from' state
    for _from, _event, _to in fsm.history:
        visited.append(_to)
    assert visited == expected_states, (
        f"Expected path {[s.value for s in expected_states]}, " f"got {[s.value for s in visited]}"
    )


def _assert_events_fired(fsm: FSMController, expected_events: list[Event]) -> None:
    """Assert the FSM fired the exact sequence of events."""
    actual = [e for _, e, _ in fsm.history]
    assert actual == expected_events, (
        f"Expected events {[e.value for e in expected_events]}, " f"got {[e.value for e in actual]}"
    )


# ===========================================================================
# Happy Paths
# ===========================================================================


class TestHappyPaths:
    """F1, F2: Normal LOW and MEDIUM flows."""

    def test_f1_normal_low(self, fsm: FSMController, classifier: MockPhase1Classifier) -> None:
        """F1: L->A->D->De->L  (LOW, no companion phase).

        Events: MESSAGE_RECEIVED, PHASE1_COMPLETE, DISPATCH_COMPLETE, RESPONSE_DELIVERED
        Transitions: T1, T3, T8, T12
        """
        # T1: LISTENING -> ACKING
        new, actions = fsm.transition(Event.MESSAGE_RECEIVED)
        assert new is State.ACKING
        assert Action.RUN_PHASE1 in actions

        # Classify
        result = classifier.classify("What's the weather in Lake Tahoe?")
        assert result.tier == "LOW"
        assert result.gaps == []

        # T3: ACKING -> DISPATCHING
        new, actions = fsm.transition(Event.PHASE1_COMPLETE)
        assert new is State.DISPATCHING
        assert actions == [Action.ROUTE_BY_TIER]

        # T8: DISPATCHING -> DELIVERING (LOW direct)
        new, actions = fsm.transition(Event.DISPATCH_COMPLETE)
        assert new is State.DELIVERING
        assert actions == [Action.ASSEMBLE_RESPONSE]

        # T12: DELIVERING -> LISTENING
        new, actions = fsm.transition(Event.RESPONSE_DELIVERED)
        assert new is State.LISTENING
        assert actions == [Action.FLUSH_AND_CHECKPOINT]

        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )
        _assert_events_fired(
            fsm,
            [
                Event.MESSAGE_RECEIVED,
                Event.PHASE1_COMPLETE,
                Event.DISPATCH_COMPLETE,
                Event.RESPONSE_DELIVERED,
            ],
        )

    def test_f2_normal_medium(self, fsm: FSMController, classifier: MockPhase1Classifier) -> None:
        """F2: L->A->D->Co->P->De->L  (MEDIUM, full companion + progress).

        Events: MR, P1C, PAS, PR, DC, RD
        Transitions: T1, T3, T7, T9, T11, T12
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify("Check for kid-friendly activities near Lake Tahoe")
        assert result.tier == "MEDIUM"

        fsm.transition(Event.PHASE1_COMPLETE)
        # T7: DISPATCHING -> COMPANIONING
        new, actions = fsm.transition(Event.PRELIMINARY_ACK_SENT)
        assert new is State.COMPANIONING
        assert Action.START_TOOL_LOOP in actions

        # T9: COMPANIONING -> PROGRESSING
        new, _ = fsm.transition(Event.PROGRESS_RECEIVED)
        assert new is State.PROGRESSING

        # T11: PROGRESSING -> DELIVERING
        new, _ = fsm.transition(Event.DISPATCH_COMPLETE)
        assert new is State.DELIVERING

        # T12: DELIVERING -> LISTENING
        fsm.transition(Event.RESPONSE_DELIVERED)
        assert fsm.state is State.LISTENING

        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )


# ===========================================================================
# Clarification Flows
# ===========================================================================


class TestClarificationFlows:
    """F4, F5: Single-round and max-rounds clarification."""

    def test_f4_clarification_single(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F4: L->A->Cl->A->D->Co->P->De->L  (1 clarification round).

        Events: MR, GD, CR, P1C, PAS, PR, DC, RD
        Transitions: T1, T4, T5, T3, T7, T9, T11, T12
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify("Plan our hotel stay at Lake Tahoe")
        assert result.tier == "MEDIUM"
        assert len(result.gaps) > 0  # has gaps

        # T4: ACKING -> CLARIFYING
        new, actions = fsm.transition(Event.GAPS_DETECTED)
        assert new is State.CLARIFYING
        assert actions == [Action.SEND_CLARIFICATION]

        # T5: CLARIFYING -> ACKING (user clarifies)
        new, actions = fsm.transition(Event.CLARIFICATION_RECEIVED)
        assert new is State.ACKING
        assert actions == [Action.MERGE_CLARIFICATION]

        # Now reclassify with enriched context, proceed
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.CLARIFYING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f5_max_clarification(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F5: 3 clarification rounds -> MAX_ROUNDS_REACHED -> D->De->L.

        Events: MR, GD, CR, GD, CR, GD, MRR, DC, RD
        Transitions: T1, T4, T5, T4, T5, T4, T6, T8, T12
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify("Book something special for Mom's anniversary dinner")
        assert result.tier == "MEDIUM"
        assert len(result.gaps) > 0

        # Round 1
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.CLARIFICATION_RECEIVED)

        # Round 2
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.CLARIFICATION_RECEIVED)

        # Round 3 -> max rounds
        fsm.transition(Event.GAPS_DETECTED)
        new, actions = fsm.transition(Event.MAX_ROUNDS_REACHED)
        assert new is State.DISPATCHING
        assert Action.FORCE_PROCEED in actions
        assert Action.ROUTE_BY_TIER in actions

        # Direct deliver (force-proceeded)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.CLARIFYING,
                State.ACKING,  # round 1
                State.CLARIFYING,
                State.ACKING,  # round 2
                State.CLARIFYING,
                State.DISPATCHING,  # round 3 -> forced
                State.DELIVERING,
                State.LISTENING,
            ],
        )


# ===========================================================================
# Interrupt Flows
# ===========================================================================


class TestInterruptFlows:
    """F6, F7, F8, F10: Interrupts at DISPATCHING, COMPANIONING, PROGRESSING, CLARIFYING."""

    def test_f6_interrupt_dispatching(self, fsm: FSMController) -> None:
        """F6: L->A->D(INT)->IH->A->D->De->L

        Interrupt at DISPATCHING, handle, re-enter, complete LOW.
        Transitions: T1, T3, T13a, T14, T3, T8, T12
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        assert fsm.state is State.DISPATCHING
        assert fsm.is_interruptible()

        # T13a: DISPATCHING -> INTERRUPT_HANDLING
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert Action.CANCEL_INFLIGHT in actions
        assert Action.PARTIAL_FLUSH in actions

        # T14: INTERRUPT_HANDLING -> ACKING
        new, actions = fsm.transition(Event.INTERRUPT_HANDLED)
        assert new is State.ACKING
        assert actions == [Action.REENTER_ACKING]

        # Re-classify the interrupt message and complete
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f7_interrupt_companioning(self, fsm: FSMController) -> None:
        """F7: L->A->D->Co(INT)->IH->A->D->Co->P->De->L

        Interrupt at COMPANIONING, handle, re-enter, complete MEDIUM.
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        assert fsm.state is State.COMPANIONING
        assert fsm.is_interruptible()

        # T13b: COMPANIONING -> INTERRUPT_HANDLING
        fsm.transition(Event.INTERRUPT_DETECTED)
        assert fsm.state is State.INTERRUPT_HANDLING

        # T14: Handle and re-enter
        fsm.transition(Event.INTERRUPT_HANDLED)
        assert fsm.state is State.ACKING

        # Complete MEDIUM path
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f8_interrupt_progressing(self, fsm: FSMController) -> None:
        """F8: L->A->D->Co->P(INT)->IH->A->D->Co->P->De->L

        Interrupt at PROGRESSING with partial results; handle and complete.
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        assert fsm.state is State.PROGRESSING
        assert fsm.is_interruptible()

        # T13c: PROGRESSING -> INTERRUPT_HANDLING
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert Action.PARTIAL_FLUSH in actions  # partial results preserved

        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f10_interrupt_clarifying(self, fsm: FSMController) -> None:
        """F10: L->A->Cl(INT)->IH->A->D->De->L

        Interrupt at CLARIFYING (topic change).
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.GAPS_DETECTED)
        assert fsm.state is State.CLARIFYING
        assert fsm.is_interruptible()

        # T13d: CLARIFYING -> INTERRUPT_HANDLING
        fsm.transition(Event.INTERRUPT_DETECTED)
        assert fsm.state is State.INTERRUPT_HANDLING

        # Handle interrupt, reclassify new topic
        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.CLARIFYING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )


# ===========================================================================
# Edge Cases
# ===========================================================================


class TestEdgeCases:
    """F11, F17, F18: Non-interruptible, multi-message, clarify+interrupt."""

    def test_f11_non_interruptible(self, fsm: FSMController) -> None:
        """F11: DELIVERING rejects INTERRUPT_DETECTED; after delivery, process queued msg.

        1. Drive FSM to DELIVERING
        2. Attempt interrupt -> InvalidTransitionError (non-interruptible)
        3. Complete delivery, then process queued message as new turn
        """
        # Get to DELIVERING
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        assert fsm.state is State.DELIVERING
        assert not fsm.is_interruptible()

        # Attempt interrupt -> rejected
        with pytest.raises(InvalidTransitionError) as exc_info:
            fsm.transition(Event.INTERRUPT_DETECTED)
        assert exc_info.value.state is State.DELIVERING

        # Complete delivery
        fsm.transition(Event.RESPONSE_DELIVERED)
        assert fsm.state is State.LISTENING

        # Process queued message as new turn
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)
        assert fsm.state is State.LISTENING

    def test_f17_multi_message(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F17: Multi-message batch merged, not treated as interrupt.

        Two messages arrive, merged into single classification, LOW path.
        Events: MR(+merge), P1C, DC, RD
        """
        # First message arrives
        fsm.transition(Event.MESSAGE_RECEIVED)

        # Classify merged messages
        merged = "What's checkout time at the Hyatt? Also, is the pool heated?"
        result = classifier.classify(merged)
        assert result.tier == "LOW"

        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f18_clarify_then_interrupt(self, fsm: FSMController) -> None:
        """F18: Clarify round 1 succeeds, interrupt during round 2.

        L->A->Cl->A->Cl(INT)->IH->A->D->De->L
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        # Round 1: clarify + answer
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.CLARIFICATION_RECEIVED)

        # Round 2: more gaps, then interrupt before user answers
        fsm.transition(Event.GAPS_DETECTED)
        assert fsm.state is State.CLARIFYING

        # Interrupt arrives
        fsm.transition(Event.INTERRUPT_DETECTED)
        assert fsm.state is State.INTERRUPT_HANDLING

        # Handle and complete with new topic
        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.CLARIFYING,
                State.ACKING,  # round 1
                State.CLARIFYING,
                State.INTERRUPT_HANDLING,  # interruted round 2
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )


# ===========================================================================
# Safety Flows
# ===========================================================================


class TestSafetyFlows:
    """F12, F13, F14: Crisis bypass, RED safety, AMBER safety."""

    def test_f12_crisis_bypass(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F12: L->A(CRISIS)->De->L  Crisis bypass, no tools, static response.

        Transitions: T1, T2, T12
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify(
            "My kid just fell and is bleeding at the ski slope",
        )
        assert result.safety_band == "CRISIS"

        # T2: ACKING -> DELIVERING (crisis bypass)
        new, actions = fsm.transition(Event.CRISIS_DETECTED)
        assert new is State.DELIVERING
        assert actions == [Action.CRISIS_RESPONSE]

        # T12: DELIVERING -> LISTENING
        fsm.transition(Event.RESPONSE_DELIVERED)
        assert fsm.state is State.LISTENING

        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f13_red_safety(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F13: RED safety band -- action tools blocked, read/cognitive only.

        Same FSM path as MEDIUM (L->A->D->Co->P->De->L) but action tools
        would be filtered at runtime.  Here we verify:
        1. Classifier returns RED
        2. FSM path is valid MEDIUM
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify(
            "Look up the ER number and directions to Barton Memorial Hospital",
        )
        assert result.safety_band == "RED"
        assert result.tier == "MEDIUM"

        # MEDIUM path with RED safety (tool filtering is runtime, not FSM)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f14_amber_safety(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F14: AMBER safety band -- normal routing, enhanced logging flag.

        Same FSM path as LOW.  Verify classifier returns AMBER.
        """
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify(
            "Does anyone have food allergies I should know about?",
        )
        assert result.safety_band == "AMBER"

        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )


# ===========================================================================
# Degradation Flows
# ===========================================================================


class TestDegradationFlows:
    """F15, F24, F26, F27: Watchdog, full fallback, classifier failure, write failure."""

    def test_f15_watchdog_timeout(self, fsm: FSMController) -> None:
        """F15: Watchdog timer fires interrupt during PROGRESSING.

        L->A->D->Co->P(TIMEOUT/INT)->IH->A
        System-initiated interrupt, same FSM mechanics as user interrupt.
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        assert fsm.state is State.PROGRESSING

        # Watchdog fires INTERRUPT_DETECTED (system-initiated)
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert Action.CANCEL_INFLIGHT in actions

        # Handle interrupt
        fsm.transition(Event.INTERRUPT_HANDLED)
        assert fsm.state is State.ACKING

        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
            ],
        )

    def test_f24_full_fallback(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F24: All circuit breakers open -> canned fallback response.

        FSM path is same as LOW: L->A->D->De->L.
        The CB failure is handled at tool execution level, not FSM level.
        Verify force_cb_open flag is set on classifier.
        """
        classifier.force_cb_open = True
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify("Book a private boat tour on the lake")
        assert result.entities.get("_force_cb_open") == "true"

        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.DELIVERING,
                State.LISTENING,
            ],
        )

    def test_f26_classifier_failure(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F26: Phase 1 classifier throws -> heuristic fallback.

        classify_with_fallback() catches ClassifierError and returns degraded result.
        FSM path is the same once classification completes.
        """
        classifier.raise_on_next = True
        fsm.transition(Event.MESSAGE_RECEIVED)

        result = classifier.classify_with_fallback(
            "What time does the gondola start tomorrow?",
        )
        assert result.classifier_degraded is True
        assert result.confidence < 0.5  # low confidence on fallback

        # FSM continues normally after heuristic fallback
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING

    def test_f26_classifier_raw_error(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F26 variant: raw classify() without fallback raises ClassifierError."""
        classifier.raise_on_next = True
        with pytest.raises(ClassifierError):
            classifier.classify("Anything")

    def test_f27_write_failure(
        self,
        fsm: FSMController,
        classifier: MockPhase1Classifier,
    ) -> None:
        """F27: SessionState write failure -- MutationGuard rejects.

        FSM path is unchanged; write failure is handled at tool level.
        The FSM still completes its path: L->A->D->De->L.
        """
        from k1.sessionstate import SessionStateFactory  # noqa: PLC0415
        from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet  # noqa: PLC0415

        manager = SessionStateFactory.create_for_testing(session_id="test-f27")
        cognitive = CognitiveToolSet(manager)

        # Simulate bad operation -> MutationGuard rejects
        result = cognitive._write("beliefs_active", "not_a_real_op", {"foo": "bar"})
        assert result["success"] is False
        assert result["rejection_reason"] is not None

        # FSM path is unaffected by write failure
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        fsm.transition(Event.RESPONSE_DELIVERED)

        assert fsm.state is State.LISTENING


# ===========================================================================
# Control Flows
# ===========================================================================


class TestControlFlows:
    """F31, F32: User cancel and clarification timeout."""

    def test_f31_user_cancel(self, fsm: FSMController) -> None:
        """F31: Explicit user cancel during PROGRESSING, no replacement topic.

        L->A->D->Co->P(CANCEL/INT)->IH->A
        Cancel is modeled as an interrupt with no follow-up topic.
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        assert fsm.state is State.PROGRESSING

        # User says "cancel" -> INTERRUPT_DETECTED
        fsm.transition(Event.INTERRUPT_DETECTED)
        assert fsm.state is State.INTERRUPT_HANDLING

        # Handle interrupt
        fsm.transition(Event.INTERRUPT_HANDLED)
        assert fsm.state is State.ACKING

        # Cancel means no replacement topic -- goes straight to close-out
        # In the PoC, the loop would choose to deliver a cancel ack
        # FSM mechanically: ACKING can receive a synthetic PHASE1_COMPLETE
        # then immediately deliver or classifier detects "cancel" intent
        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.DISPATCHING,
                State.COMPANIONING,
                State.PROGRESSING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
            ],
        )

    def test_f32_clarification_timeout(self, fsm: FSMController) -> None:
        """F32: Timeout during CLARIFYING -> abandonment.

        L->A->Cl(TIMEOUT)
        Timeout fires INTERRUPT_DETECTED from CLARIFYING, then the turn
        is abandoned (INTERRUPT_HANDLED -> session cleanup).
        In the PoC the timeout is simulated as an interrupt.
        """
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.GAPS_DETECTED)
        assert fsm.state is State.CLARIFYING

        # Timeout fires interrupt
        fsm.transition(Event.INTERRUPT_DETECTED)
        assert fsm.state is State.INTERRUPT_HANDLING

        # Interrupt handled -- turn abandoned, no replacement topic
        fsm.transition(Event.INTERRUPT_HANDLED)
        assert fsm.state is State.ACKING

        _assert_path(
            fsm,
            [
                State.LISTENING,
                State.ACKING,
                State.CLARIFYING,
                State.INTERRUPT_HANDLING,
                State.ACKING,
            ],
        )
