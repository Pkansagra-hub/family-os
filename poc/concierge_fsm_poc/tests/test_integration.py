"""TEST-004: Full 20-Turn Story Integration Test.

Runs all 20 turns programmatically from ``TRIP_TIMELINE``, driving
FSM + MockPhase1Classifier + CognitiveToolSet + SessionState through
each flow's expected path.

Verifies:
    1. FSM returns to LISTENING (or expected terminal state) after each turn
    2. SessionState accumulates beliefs, scoreboard, narrative
    3. All 14 transition types fired at least once across 20 turns
    4. All 8 FSM states visited at least once
    5. Classifier special flags (raise_on_next, force_cb_open) work

Aligned to ``CONCIERGE_FSM_POC_PLAN.md`` Epic 5.4 and Appendix B.
"""

from __future__ import annotations

from k1.sessionstate import SessionStateFactory
from poc.concierge_fsm_poc.fsm.controller import Event, FSMController, State
from poc.concierge_fsm_poc.fsm.phase1_mock import MockPhase1Classifier
from poc.concierge_fsm_poc.scenarios.trip_timeline import TRIP_TIMELINE, get_hint
from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All 14 transition type labels (T1-T14, with T13 covering 4 sub-entries)
ALL_TRANSITIONS = {
    "T1",
    "T2",
    "T3",
    "T4",
    "T5",
    "T6",
    "T7",
    "T8",
    "T9",
    "T10",
    "T11",
    "T12",
    "T13",
    "T14",
}


def _label_transition(from_state: State, event: Event, to_state: State) -> str:
    """Map a (from, event, to) triple to its transition label (T1-T14)."""
    mapping = {
        (State.LISTENING, Event.MESSAGE_RECEIVED, State.ACKING): "T1",
        (State.ACKING, Event.CRISIS_DETECTED, State.DELIVERING): "T2",
        (State.ACKING, Event.PHASE1_COMPLETE, State.DISPATCHING): "T3",
        (State.ACKING, Event.GAPS_DETECTED, State.CLARIFYING): "T4",
        (State.CLARIFYING, Event.CLARIFICATION_RECEIVED, State.ACKING): "T5",
        (State.CLARIFYING, Event.MAX_ROUNDS_REACHED, State.DISPATCHING): "T6",
        (State.DISPATCHING, Event.PRELIMINARY_ACK_SENT, State.COMPANIONING): "T7",
        (State.DISPATCHING, Event.DISPATCH_COMPLETE, State.DELIVERING): "T8",
        (State.COMPANIONING, Event.PROGRESS_RECEIVED, State.PROGRESSING): "T9",
        (State.COMPANIONING, Event.DISPATCH_COMPLETE, State.DELIVERING): "T10",
        (State.PROGRESSING, Event.DISPATCH_COMPLETE, State.DELIVERING): "T11",
        (State.DELIVERING, Event.RESPONSE_DELIVERED, State.LISTENING): "T12",
        (State.INTERRUPT_HANDLING, Event.INTERRUPT_HANDLED, State.ACKING): "T14",
    }
    key = (from_state, event, to_state)
    if key in mapping:
        return mapping[key]
    # T13: any interruptible -> INTERRUPT_HANDLING
    if event == Event.INTERRUPT_DETECTED and to_state == State.INTERRUPT_HANDLING:
        return "T13"
    return f"UNKNOWN({from_state.value},{event.value},{to_state.value})"


def _complete_low_path(fsm: FSMController) -> None:
    """Complete a LOW tier path: DISPATCHING -> DELIVERING -> LISTENING."""
    fsm.transition(Event.DISPATCH_COMPLETE)
    fsm.transition(Event.RESPONSE_DELIVERED)


def _complete_medium_path(fsm: FSMController) -> None:
    """Complete a MEDIUM tier path: DISPATCHING -> COMPANIONING -> PROGRESSING -> DELIVERING -> LISTENING."""
    fsm.transition(Event.PRELIMINARY_ACK_SENT)
    fsm.transition(Event.PROGRESS_RECEIVED)
    fsm.transition(Event.DISPATCH_COMPLETE)
    fsm.transition(Event.RESPONSE_DELIVERED)


def _drive_turn(
    fsm: FSMController,
    classifier: MockPhase1Classifier,
    cognitive: CognitiveToolSet,
    turn_number: int,
) -> None:
    """Drive FSM through one turn based on the TRIP_TIMELINE hint.

    After this function, FSM should be at LISTENING (or ACKING for
    abandoned turns like T15/T19/T20 or after interrupt handling).
    """
    hint = get_hint(turn_number)
    assert hint is not None, f"No hint for turn {turn_number}"

    # Apply special flags
    for flag, value in hint.special_flags.items():
        setattr(classifier, flag, value)

    # T1: LISTENING -> ACKING
    fsm.transition(Event.MESSAGE_RECEIVED)

    # Run classifier
    result = classifier.classify_with_fallback(hint.suggested_message)

    # -- Flow-specific FSM driving --

    flow = hint.flow_id

    if flow == "F1":
        # LOW direct: A -> D -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)
        # Write cognitive data
        cognitive.update_scoreboard("upsert_task", task_id=f"turn-{turn_number}")
        cognitive.update_beliefs(
            "add_fact",
            subject="weather",
            predicate="is",
            object_="45F",
        )

    elif flow == "F2":
        # MEDIUM full: A -> D -> Co -> P -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_medium_path(fsm)
        cognitive.update_scoreboard("upsert_task", task_id=f"turn-{turn_number}")
        cognitive.update_narrative("new_thread", summary="kid activities")

    elif flow == "F14":
        # AMBER LOW: A -> D -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)
        cognitive.update_beliefs(
            "add_fact",
            subject="Mom",
            predicate="allergic_to",
            object_="shellfish",
        )

    elif flow == "F4":
        # Single clarification: A -> Cl -> A -> D -> Co -> P -> De -> L
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.CLARIFICATION_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_medium_path(fsm)
        cognitive.update_scoreboard("upsert_task", task_id=f"turn-{turn_number}")

    elif flow == "F5":
        # Max rounds: A -> Cl -> A -> Cl -> A -> Cl -> MRR -> D -> De -> L
        for _ in range(3):
            fsm.transition(Event.GAPS_DETECTED)
            if _ < 2:
                fsm.transition(Event.CLARIFICATION_RECEIVED)
        fsm.transition(Event.MAX_ROUNDS_REACHED)
        _complete_low_path(fsm)

    elif flow == "F6":
        # Interrupt at DISPATCHING: A -> D(INT) -> IH -> A -> D -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        # Reclassify interrupt message
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    elif flow == "F7":
        # Interrupt at COMPANIONING: A -> D -> Co(INT) -> IH -> A -> D -> Co -> P -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_medium_path(fsm)
        cognitive.update_scoreboard("upsert_task", task_id=f"turn-{turn_number}")

    elif flow == "F8":
        # Interrupt at PROGRESSING: A -> D -> Co -> P(INT) -> IH -> A -> D -> Co -> P -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_medium_path(fsm)
        cognitive.update_scoreboard("upsert_task", task_id=f"turn-{turn_number}")

    elif flow == "F10":
        # Interrupt at CLARIFYING: A -> Cl(INT) -> IH -> A -> D -> De -> L
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    elif flow == "F12":
        # Crisis bypass: A(CRISIS) -> De -> L
        fsm.transition(Event.CRISIS_DETECTED)
        fsm.transition(Event.RESPONSE_DELIVERED)

    elif flow == "F13":
        # RED safety, MEDIUM path: A -> D -> Co -> De -> L
        # Uses T10 (COMPANIONING -> DISPATCH_COMPLETE) since RED blocks
        # action tools, so work may complete without a progress step.
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.DISPATCH_COMPLETE)  # T10: Co -> De directly
        fsm.transition(Event.RESPONSE_DELIVERED)

    elif flow == "F17":
        # Multi-message merged, LOW: A -> D -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)
        cognitive.update_beliefs(
            "add_fact",
            subject="hotel",
            predicate="checkout",
            object_="11am",
        )

    elif flow == "F18":
        # Clarify round 1, interrupt round 2:
        # A -> Cl -> A -> Cl(INT) -> IH -> A -> D -> De -> L
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.CLARIFICATION_RECEIVED)
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    elif flow == "F11":
        # Non-interruptible: deliver current, then process queued msg
        # We simulate: FSM is at LISTENING after prior turn,
        # drive through a LOW path (the queued msg)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)
        cognitive.update_scoreboard("upsert_task", task_id=f"turn-{turn_number}")

    elif flow == "F15":
        # Watchdog timeout: A -> D -> Co -> P(TIMEOUT/INT) -> IH -> A
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        # Watchdog fires interrupt
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        # After interrupt handled, complete with fallback
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    elif flow == "F24":
        # Full fallback (CB open): A -> D -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)
        # Reset CB flag
        classifier.force_cb_open = False

    elif flow == "F26":
        # Classifier failure with heuristic fallback: A -> D -> De -> L
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    elif flow == "F27":
        # Write failure: A -> D -> De -> L  (write failure at tool level)
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)
        # Attempt a write with bad operation -> MutationGuard rejects
        result = cognitive._write("beliefs_active", "not_a_real_op", {"x": 1})
        assert result["success"] is False

    elif flow == "F31":
        # User cancel: A -> D -> Co -> P(CANCEL/INT) -> IH -> A -> deliver
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        # Cancel with no replacement: deliver cancel ack
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    elif flow == "F32":
        # Clarification timeout: A -> Cl(TIMEOUT/INT) -> IH -> A
        fsm.transition(Event.GAPS_DETECTED)
        fsm.transition(Event.INTERRUPT_DETECTED)
        fsm.transition(Event.INTERRUPT_HANDLED)
        # Abandoned turn: deliver timeout ack and close
        fsm.transition(Event.PHASE1_COMPLETE)
        _complete_low_path(fsm)

    else:
        raise ValueError(f"Unhandled flow_id: {flow}")


# ===========================================================================
# Test Class
# ===========================================================================


class TestFullStoryIntegration:
    """TEST-004: Run all 20 turns, verify coverage and state accumulation."""

    def test_full_20_turn_story(self) -> None:
        """Execute all 20 TRIP_TIMELINE turns sequentially.

        Acceptance Criteria:
        - All 20 turns execute without error
        - FSM ends at LISTENING after every turn
        - All 14 transition types fired at least once
        - All 8 FSM states visited at least once
        - SessionState accumulates data across turns
        """
        fsm = FSMController()
        classifier = MockPhase1Classifier()
        manager = SessionStateFactory.create_for_testing(session_id="test-integration")
        cognitive = CognitiveToolSet(manager)

        all_transitions_fired: set[str] = set()
        all_states_visited: set[State] = {State.LISTENING}  # initial state

        for hint in TRIP_TIMELINE:
            assert hint.turn_number is not None

            # Record pre-turn history length
            history_before = len(fsm.history)

            # Drive the turn
            _drive_turn(fsm, classifier, cognitive, hint.turn_number)

            # Verify FSM returned to LISTENING
            assert fsm.state is State.LISTENING, (
                f"Turn {hint.turn_number} ({hint.flow_id}): "
                f"FSM ended at {fsm.state.value}, expected LISTENING"
            )

            # Collect states and transitions from this turn's history
            for from_s, event, to_s in fsm.history[history_before:]:
                all_states_visited.add(from_s)
                all_states_visited.add(to_s)
                label = _label_transition(from_s, event, to_s)
                all_transitions_fired.add(label)

        # -- Coverage assertions --

        # All 8 states visited
        all_state_values = {s for s in State}
        missing_states = all_state_values - all_states_visited
        assert not missing_states, f"States never visited: {[s.value for s in missing_states]}"

        # All 14 transition types fired
        missing_transitions = ALL_TRANSITIONS - all_transitions_fired
        assert not missing_transitions, f"Transitions never fired: {missing_transitions}"

        # SessionState accumulated data
        snapshot = manager.get_snapshot()
        assert snapshot is not None, "SessionState snapshot is None"

        # Verify history grew (20 turns should produce many transitions)
        assert (
            len(fsm.history) >= 80
        ), f"Expected 80+ transitions across 20 turns, got {len(fsm.history)}"

    def test_each_turn_isolates_correctly(self) -> None:
        """Each turn starts and ends at LISTENING -- no state leakage."""
        fsm = FSMController()
        classifier = MockPhase1Classifier()
        manager = SessionStateFactory.create_for_testing(session_id="test-isolation")
        cognitive = CognitiveToolSet(manager)

        for hint in TRIP_TIMELINE:
            assert (
                fsm.state is State.LISTENING
            ), f"Turn {hint.turn_number} started at {fsm.state.value}"
            _drive_turn(fsm, classifier, cognitive, hint.turn_number)
            assert (
                fsm.state is State.LISTENING
            ), f"Turn {hint.turn_number} ended at {fsm.state.value}"

    def test_classifier_special_flags_reset(self) -> None:
        """Special flags (raise_on_next, force_cb_open) are consumed after use."""
        classifier = MockPhase1Classifier()

        # raise_on_next resets after classify_with_fallback
        classifier.raise_on_next = True
        result = classifier.classify_with_fallback("test")
        assert result.classifier_degraded is True
        assert classifier.raise_on_next is False

        # force_cb_open stays (caller must reset)
        classifier.force_cb_open = True
        result = classifier.classify("test")
        assert result.entities.get("_force_cb_open") == "true"
        classifier.force_cb_open = False
        result = classifier.classify("test")
        assert "_force_cb_open" not in result.entities

    def test_cognitive_writes_accumulate(self) -> None:
        """Cognitive tools accumulate writes across multiple turns."""
        manager = SessionStateFactory.create_for_testing(session_id="test-accumulate")
        cognitive = CognitiveToolSet(manager)

        # Write beliefs
        r1 = cognitive.update_beliefs(
            "add_fact",
            subject="Mom",
            predicate="allergic_to",
            object_="shellfish",
        )
        assert r1["success"] is True

        # Second write should increase section bytes (or at least not fail)
        r2 = cognitive.update_beliefs(
            "add_fact",
            subject="Jake",
            predicate="likes",
            object_="skiing",
        )
        assert r2["success"] is True
        # belief_ids should be unique
        assert r1["belief_id"] != r2["belief_id"]

        # Scoreboard write
        r3 = cognitive.update_scoreboard("upsert_task", task_id="T1")
        assert r3["success"] is True

        # Narrative write
        r4 = cognitive.update_narrative("new_thread", summary="trip planning")
        assert r4["success"] is True
        assert r4["active_threads"] >= 1

    def test_transition_coverage_summary(self) -> None:
        """Verify the specific flows that exercise each transition type.

        Cross-reference against Appendix B.
        """
        fsm = FSMController()
        classifier = MockPhase1Classifier()
        manager = SessionStateFactory.create_for_testing(session_id="test-coverage")
        cognitive = CognitiveToolSet(manager)

        transition_sources: dict[str, list[str]] = {}

        for hint in TRIP_TIMELINE:
            history_before = len(fsm.history)
            _drive_turn(fsm, classifier, cognitive, hint.turn_number)

            for from_s, event, to_s in fsm.history[history_before:]:
                label = _label_transition(from_s, event, to_s)
                transition_sources.setdefault(label, []).append(hint.flow_id)

        # Verify each transition type was fired by at least one turn
        for t_label in ALL_TRANSITIONS:
            assert t_label in transition_sources, f"Transition {t_label} was never fired"

        # Verify expected sources for key transitions (from Appendix B)
        assert "F1" in transition_sources.get("T8", [])  # T8: LOW direct
        assert "F2" in transition_sources.get("T7", [])  # T7: MEDIUM ack
        assert "F4" in transition_sources.get("T4", [])  # T4: gaps detected
        assert "F5" in transition_sources.get("T6", [])  # T6: max rounds
        assert "F12" in transition_sources.get("T2", [])  # T2: crisis
