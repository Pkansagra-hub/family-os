"""
tests.poc.test_m02_e21_guard_matrix -- E2.1 FSM Guard Matrix Conformance.

Validates:
    2.1.1  FULL_GUARD_TABLE completeness and structure
    2.1.2  Guard dispatch wiring (_guard_dispatch, _publish_dead_letter)
    2.1.3  CANCELLING transition via _transition() (not force-set)
    2.1.4  _handle_interrupt deduplication
    2.1.5  No duplicate DAG subscription
    2.1.6  Hardcoded constants replaced (front_lock, controller)
    2.1.7  Guard conformance invariants
"""

from __future__ import annotations

import json

from k1.concierge.bus.builders import (
    build_task_cancel,
    build_tool_started,
    build_user_input,
)
from k1.concierge.bus.setup import ACTOR_BACK, ACTOR_FRONT
from k1.concierge.bus.topics import (
    ALL_TOPICS,
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_DAG_COMPLETED,
    TOPIC_DEAD_LETTER,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_PROACTIVE_FILL,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_STARTED,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.fsm.transition_table import (
    FULL_GUARD_TABLE,
    SUBSCRIBED_TOPICS,
    GuardAction,
    get_guard_action,
    is_legal,
    target_state,
)

STATE_UPDATED_TOPIC = "k1.session.state.updated.v1"


def _parse_captured_payload(envelope) -> dict:
    """Parse JSON payload from a captured envelope."""
    try:
        return json.loads(envelope.payload) if envelope.payload else {}
    except Exception:
        return {}


# =============================================================================
# 2.1.1: FULL_GUARD_TABLE completeness
# =============================================================================


class TestFullGuardTableCompleteness:
    """FULL_GUARD_TABLE covers every state and every subscribed topic."""

    def test_covers_all_states(self) -> None:
        """Every ConciergeState enum member has an entry in FULL_GUARD_TABLE."""
        table_states = set(FULL_GUARD_TABLE.keys())
        enum_states = set(ConciergeState)
        assert table_states == enum_states, (
            f"Missing states: {enum_states - table_states}, "
            f"Extra states: {table_states - enum_states}"
        )

    def test_covers_all_subscribed_topics(self) -> None:
        """Every state entry covers every topic in SUBSCRIBED_TOPICS."""
        for state in ConciergeState:
            state_topics = set(FULL_GUARD_TABLE[state].keys())
            missing = SUBSCRIBED_TOPICS - state_topics
            assert not missing, f"State {state.name} missing topics: {missing}"

    def test_includes_dag_completed(self) -> None:
        """DAG_COMPLETED (normalizer topic) is in every state row."""
        for state in ConciergeState:
            assert (
                TOPIC_DAG_COMPLETED in FULL_GUARD_TABLE[state]
            ), f"State {state.name} missing TOPIC_DAG_COMPLETED"

    def test_cell_count_minimum(self) -> None:
        """At least 11 states * 18 topics = 198 cells."""
        total = sum(len(topics) for topics in FULL_GUARD_TABLE.values())
        assert total >= 198, f"Expected >= 198 cells, got {total}"

    def test_no_unknown_guard_actions(self) -> None:
        """Every cell value is a valid (GuardAction, state|None) tuple."""
        valid_actions = set(GuardAction)
        for state, topics in FULL_GUARD_TABLE.items():
            for topic, (action, tgt) in topics.items():
                assert (
                    action in valid_actions
                ), f"Invalid action {action!r} for ({state.name}, {topic})"
                if action == GuardAction.TRANSITION:
                    assert tgt is None or isinstance(
                        tgt, ConciergeState
                    ), f"TRANSITION cell ({state.name}, {topic}) must have state target or None"
                else:
                    assert (
                        tgt is None
                    ), f"Non-TRANSITION cell ({state.name}, {topic}) must have None target"


class TestSubscribedTopics:
    """SUBSCRIBED_TOPICS frozenset correctness."""

    def test_is_frozenset(self) -> None:
        assert isinstance(SUBSCRIBED_TOPICS, frozenset)

    def test_has_20_topics(self) -> None:
        """28 unique subscribed topics (original set minus 2 dead E5 clarification topics retired in E4 cleanup)."""
        assert len(SUBSCRIBED_TOPICS) == 28

    def test_all_are_valid_bus_topics(self) -> None:
        """Every member of SUBSCRIBED_TOPICS is a known ALL_TOPICS member."""
        for topic in SUBSCRIBED_TOPICS:
            assert topic in ALL_TOPICS, f"{topic} not in ALL_TOPICS"


# =============================================================================
# 2.1.1: get_guard_action helper
# =============================================================================


class TestGetGuardAction:
    """get_guard_action lookup function."""

    def test_known_transition_cell(self) -> None:
        action, tgt = get_guard_action(ConciergeState.LISTENING, TOPIC_USER_INPUT)
        assert action == GuardAction.TRANSITION
        assert tgt == ConciergeState.DISPATCHING

    def test_known_dead_letter_cell(self) -> None:
        action, tgt = get_guard_action(ConciergeState.LISTENING, TOPIC_TOOL_STARTED)
        assert action == GuardAction.DEAD_LETTER
        assert tgt is None

    def test_known_passthrough_cell(self) -> None:
        action, tgt = get_guard_action(ConciergeState.LISTENING, TOPIC_FINDINGS_READY)
        assert action == GuardAction.PASSTHROUGH
        assert tgt is None

    def test_known_observe_cell(self) -> None:
        action, tgt = get_guard_action(ConciergeState.LISTENING, TOPIC_ARTIFACT_CREATED)
        assert action == GuardAction.OBSERVE
        assert tgt is None

    def test_known_queue_cell(self) -> None:
        action, tgt = get_guard_action(ConciergeState.DELIVERING, TOPIC_USER_INPUT)
        assert action == GuardAction.QUEUE
        assert tgt is None

    def test_unknown_topic_returns_dead_letter(self) -> None:
        """Unknown topic always returns DEAD_LETTER."""
        action, tgt = get_guard_action(ConciergeState.LISTENING, "bogus.topic.v1")
        assert action == GuardAction.DEAD_LETTER
        assert tgt is None

    def test_dag_completed_passthrough_all_states(self) -> None:
        """DAG_COMPLETED is PASSTHROUGH in every state (normalizer)."""
        for state in ConciergeState:
            action, _ = get_guard_action(state, TOPIC_DAG_COMPLETED)
            assert (
                action == GuardAction.PASSTHROUGH
            ), f"DAG_COMPLETED in {state.name} should be PASSTHROUGH, got {action}"


# =============================================================================
# 2.1.1: Backward compatibility with original TRANSITION_TABLE
# =============================================================================


class TestBackwardCompatibility:
    """Original TRANSITION_TABLE, is_legal(), target_state() still work."""

    def test_is_legal_listening_user_input(self) -> None:
        assert is_legal(ConciergeState.LISTENING, TOPIC_USER_INPUT) is True

    def test_is_legal_listening_bogus(self) -> None:
        assert is_legal(ConciergeState.LISTENING, "bogus") is False

    def test_target_state_listening_user_input(self) -> None:
        assert (
            target_state(ConciergeState.LISTENING, TOPIC_USER_INPUT) == ConciergeState.DISPATCHING
        )

    def test_target_state_returns_none_for_illegal(self) -> None:
        assert target_state(ConciergeState.LISTENING, "bogus") is None

    def test_transition_table_task_cancel_entries(self) -> None:
        """M2 E2.1.3: TASK_CANCEL transitions added to TRANSITION_TABLE."""
        for state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
            ConciergeState.DISPATCHING,
        ):
            assert is_legal(
                state, TOPIC_TASK_CANCEL
            ), f"TASK_CANCEL should be legal from {state.name}"
            assert target_state(state, TOPIC_TASK_CANCEL) == ConciergeState.CANCELLING

    def test_guard_table_agrees_with_transition_table(self) -> None:
        """Every TRANSITION cell in FULL_GUARD_TABLE with a bus topic trigger
        also appears in TRANSITION_TABLE (for bus topics, not synthetic triggers)."""
        for state, topics in FULL_GUARD_TABLE.items():
            for topic, (action, tgt) in topics.items():
                if action == GuardAction.TRANSITION:
                    tt_target = target_state(state, topic)
                    if tgt is None:
                        assert is_legal(state, topic), (
                            f"FULL_GUARD_TABLE ({state.name}, {topic}) is dynamic TRANSITION "
                            "but TRANSITION_TABLE says illegal"
                        )
                    else:
                        assert tt_target == tgt, (
                            f"FULL_GUARD_TABLE ({state.name}, {topic}) -> {tgt} "
                            f"but TRANSITION_TABLE -> {tt_target}"
                        )


# =============================================================================
# 2.1.2: Guard dispatch on FSM controller
# =============================================================================


class TestGuardDispatchOnFSM:
    """_guard_dispatch and _publish_dead_letter on ConciergeController."""

    def _make_fsm(self):
        from k1.concierge.bus.setup import create_poc_bus, create_poc_router
        from k1.concierge.fsm.controller import ConciergeController

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        return ConciergeController(bus=bus, router=router), bus

    def test_guard_dispatch_exists(self) -> None:
        fsm, _ = self._make_fsm()
        assert hasattr(fsm, "_guard_dispatch")
        assert callable(fsm._guard_dispatch)

    def test_guard_dispatch_returns_guard_action(self) -> None:
        fsm, _ = self._make_fsm()
        env = build_user_input({"text": "hello"})
        action = fsm._guard_dispatch(env)
        assert isinstance(action, GuardAction)

    def test_guard_dispatch_listening_user_input_is_transition(self) -> None:
        fsm, _ = self._make_fsm()
        # Default state is LISTENING
        env = build_user_input({"text": "hello"})
        action = fsm._guard_dispatch(env)
        assert action == GuardAction.TRANSITION

    def test_guard_dispatch_listening_tool_started_is_dead_letter(self) -> None:
        fsm, _ = self._make_fsm()
        env = build_tool_started({"task_id": "t1", "tool_name": "x"})
        action = fsm._guard_dispatch(env)
        assert action == GuardAction.DEAD_LETTER

    def test_publish_dead_letter_exists(self) -> None:
        fsm, _ = self._make_fsm()
        assert hasattr(fsm, "_publish_dead_letter")
        assert callable(fsm._publish_dead_letter)

    def test_publish_dead_letter_emits_to_dead_letter_topic(self) -> None:
        fsm, bus = self._make_fsm()
        env = build_tool_started({"task_id": "t1", "tool_name": "x"})
        fsm._publish_dead_letter(env, "test_reason")

        # Find the dead letter event in captured envelopes
        captured = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        assert len(captured) >= 1
        last = captured[-1]
        payload = _parse_captured_payload(last)
        assert payload.get("reason") == "test_reason"
        assert payload.get("original_topic") == TOPIC_TOOL_STARTED

    def test_dead_letter_handler_returns_early(self) -> None:
        """When guard returns DEAD_LETTER, handler must not proceed."""
        fsm, bus = self._make_fsm()
        # tool_started in LISTENING state = DEAD_LETTER
        env = build_tool_started(
            {"task_id": "t1", "tool_name": "x"},
        )
        initial_state = fsm._state
        fsm._on_tool_started(env)
        # State should not change
        assert fsm._state == initial_state
        # Dead letter should have been published
        dead_letters = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        assert len(dead_letters) >= 1


# =============================================================================
# 2.1.3: CANCELLING transition via _transition()
# =============================================================================


class TestCancellingTransition:
    """task.cancel uses _transition() instead of forced state assignment."""

    def _make_fsm(self):
        from k1.concierge.bus.setup import create_poc_bus, create_poc_router
        from k1.concierge.fsm.controller import ConciergeController

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        return ConciergeController(bus=bus, router=router), bus

    def test_cancel_from_companioning(self) -> None:
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_task_cancel({"task_id": "t1"})
        fsm._on_task_cancel(env)
        assert fsm._state == ConciergeState.CANCELLING

    def test_cancel_from_progressing(self) -> None:
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.PROGRESSING
        env = build_task_cancel({"task_id": "t1"})
        fsm._on_task_cancel(env)
        assert fsm._state == ConciergeState.CANCELLING

    def test_cancel_from_dispatching(self) -> None:
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.DISPATCHING
        env = build_task_cancel({"task_id": "t1"})
        fsm._on_task_cancel(env)
        assert fsm._state == ConciergeState.CANCELLING

    def test_cancel_emits_state_updated(self) -> None:
        """_transition() publishes state.updated (not manual publish)."""
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_task_cancel({"task_id": "t1"})
        fsm._on_task_cancel(env)
        state_updates = [
            e
            for e in bus.captured
            if e.topic == STATE_UPDATED_TOPIC
            and _parse_captured_payload(e).get("to_state") == "CANCELLING"
        ]
        assert len(state_updates) >= 1

    def test_cancel_dead_letter_in_listening(self) -> None:
        """task.cancel in LISTENING is dead-lettered by guard."""
        fsm, bus = self._make_fsm()
        # LISTENING is default state
        env = build_task_cancel({"task_id": "t1"})
        fsm._on_task_cancel(env)
        # State should NOT change to CANCELLING
        assert fsm._state == ConciergeState.LISTENING
        dead_letters = [e for e in bus.captured if e.topic == TOPIC_DEAD_LETTER]
        assert len(dead_letters) >= 1


# =============================================================================
# 2.1.4: _handle_interrupt deduplication
# =============================================================================


class TestHandleInterrupt:
    """Interrupt path extracted into _handle_interrupt."""

    def _make_fsm(self):
        from k1.concierge.bus.setup import create_poc_bus, create_poc_router
        from k1.concierge.fsm.controller import ConciergeController

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        return ConciergeController(bus=bus, router=router), bus

    def test_handle_interrupt_method_exists(self) -> None:
        fsm, _ = self._make_fsm()
        assert hasattr(fsm, "_handle_interrupt")
        assert callable(fsm._handle_interrupt)

    def test_interrupt_from_companioning(self) -> None:
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "stop that"})
        fsm._on_user_input(env)
        # Should transition through INTERRUPT_HANDLING -> DISPATCHING
        assert fsm._state == ConciergeState.DISPATCHING

    def test_interrupt_from_progressing(self) -> None:
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.PROGRESSING
        env = build_user_input({"text": "cancel"})
        fsm._on_user_input(env)
        assert fsm._state == ConciergeState.DISPATCHING

    def test_interrupt_emits_turn_started(self) -> None:
        fsm, bus = self._make_fsm()
        fsm._state = ConciergeState.COMPANIONING
        env = build_user_input({"text": "stop"})
        fsm._on_user_input(env)
        turn_started = [e for e in bus.captured if e.topic == "k1.session.turn.started.v1"]
        assert len(turn_started) >= 1


# =============================================================================
# 2.1.5: No duplicate DAG subscription
# =============================================================================


class TestNoDuplicateDagSubscription:
    """Bare string 'k1.orchestration.dag.completed' subscription removed."""

    def _make_fsm(self):
        from k1.concierge.bus.setup import create_poc_bus, create_poc_router
        from k1.concierge.fsm.controller import ConciergeController

        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        fsm = ConciergeController(bus=bus, router=router)
        return fsm, bus

    def test_no_bare_string_dag_subscription(self) -> None:
        """Subscription count confirms bare string DAG duplicate removed."""
        fsm, bus = self._make_fsm()
        # With dup removed + M6 E6.4 config-update topic + E4 HIL unification
        # (_on_hil_request) - 2 dead E5 clarification subs retired: 19 subscriptions
        assert (
            len(fsm._subscription_handles) == 19
        ), f"Expected 19 subscriptions (dup removed, +HIL unified, -2 clarification), got {len(fsm._subscription_handles)}"

    def test_dag_completed_subscription_via_constant(self) -> None:
        """Subscription count confirms no bare string duplicate."""
        fsm, bus = self._make_fsm()
        assert len(fsm._subscription_handles) == 19


# =============================================================================
# 2.1.6: Hardcoded constants replaced
# =============================================================================


class TestHardcodedConstantsReplaced:
    """No hardcoded strings for actor names or topic strings."""

    def test_controller_uses_actor_front(self) -> None:
        """controller._deliver_to_front uses ACTOR_FRONT, not 'front_half'."""
        import inspect

        from k1.concierge.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._deliver_to_front)
        assert '"front_half"' not in source, "_deliver_to_front should use ACTOR_FRONT constant"

    def test_controller_uses_actor_back(self) -> None:
        """controller._deliver_to_back uses ACTOR_BACK, not 'back_half'."""
        import inspect

        from k1.concierge.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._deliver_to_back)
        assert '"back_half"' not in source, "_deliver_to_back should use ACTOR_BACK constant"

    def test_front_lock_uses_topic_constants(self) -> None:
        """FrontLock TOPIC_PRIORITY dict uses constants, not bare strings."""
        from k1.concierge.fsm.front_lock import TOPIC_PRIORITY

        # All keys should match known topic constants
        known = {
            TOPIC_USER_INPUT,
            TOPIC_TASK_SUSPENDED,
            TOPIC_TASK_COMPLETE,
            TOPIC_TASK_FAILED,
            TOPIC_FINDINGS_READY,
            TOPIC_WEAVE_BATCH,
            TOPIC_PROACTIVE_FILL,
        }
        assert set(TOPIC_PRIORITY.keys()) == known

    def test_actor_front_matches_setup(self) -> None:
        """ACTOR_FRONT == 'front_half'."""
        assert ACTOR_FRONT == "front_half"

    def test_actor_back_matches_setup(self) -> None:
        """ACTOR_BACK == 'back_half'."""
        assert ACTOR_BACK == "back_half"


# =============================================================================
# 2.1.7: Cross-cutting guard conformance invariants
# =============================================================================


class TestGuardConformanceInvariants:
    """Structural invariants across the guard matrix."""

    def test_user_input_never_observe(self) -> None:
        """USER_INPUT should never be OBSERVE (always needs action)."""
        for state in ConciergeState:
            action, _ = get_guard_action(state, TOPIC_USER_INPUT)
            assert (
                action != GuardAction.OBSERVE
            ), f"USER_INPUT in {state.name} should not be OBSERVE"

    def test_final_response_has_transition_in_delivering(self) -> None:
        """FINAL_RESPONSE from DELIVERING must transition (to LISTENING or WEAVING)."""
        action, tgt = get_guard_action(ConciergeState.DELIVERING, TOPIC_FINAL_RESPONSE)
        assert action == GuardAction.TRANSITION
        assert tgt == ConciergeState.LISTENING

    def test_task_dispatch_transition_from_dispatching(self) -> None:
        """TASK_DISPATCH should TRANSITION from DISPATCHING."""
        action, _ = get_guard_action(ConciergeState.DISPATCHING, TOPIC_TASK_DISPATCH)
        assert action == GuardAction.TRANSITION

    def test_task_dispatch_transition_from_companioning(self) -> None:
        """TASK_DISPATCH from COMPANIONING is idempotent self-transition."""
        action, tgt = get_guard_action(ConciergeState.COMPANIONING, TOPIC_TASK_DISPATCH)
        assert action == GuardAction.TRANSITION
        assert tgt == ConciergeState.COMPANIONING

    def test_task_dispatch_dead_letter_from_most_states(self) -> None:
        """TASK_DISPATCH should be DEAD_LETTER from non-dispatch/companion states."""
        valid_dispatch_states = {ConciergeState.DISPATCHING, ConciergeState.COMPANIONING}
        for state in ConciergeState:
            if state not in valid_dispatch_states:
                action, _ = get_guard_action(state, TOPIC_TASK_DISPATCH)
                assert (
                    action == GuardAction.DEAD_LETTER
                ), f"TASK_DISPATCH should be DEAD_LETTER from {state.name}, got {action}"

    def test_affect_update_never_transition(self) -> None:
        """AFFECT_UPDATE is always observe or dead-letter, never transition."""
        for state in ConciergeState:
            action, _ = get_guard_action(state, TOPIC_AFFECT_UPDATE)
            assert action in (
                GuardAction.OBSERVE,
                GuardAction.DEAD_LETTER,
            ), f"AFFECT_UPDATE in {state.name} should be OBSERVE or DEAD_LETTER"

    def test_proactive_fill_never_transition(self) -> None:
        """PROACTIVE_FILL is always observe or dead-letter, never transition."""
        for state in ConciergeState:
            action, _ = get_guard_action(state, TOPIC_PROACTIVE_FILL)
            assert action in (
                GuardAction.OBSERVE,
                GuardAction.DEAD_LETTER,
            ), f"PROACTIVE_FILL in {state.name} should be OBSERVE or DEAD_LETTER"

    def test_cancelling_only_accepts_task_failed(self) -> None:
        """CANCELLING state should only TRANSITION on TASK_FAILED."""
        transition_topics = []
        for topic in SUBSCRIBED_TOPICS:
            action, _ = get_guard_action(ConciergeState.CANCELLING, topic)
            if action == GuardAction.TRANSITION:
                transition_topics.append(topic)
        assert transition_topics == [TOPIC_TASK_FAILED], (
            f"CANCELLING should only transition on TASK_FAILED, "
            f"got transitions on: {transition_topics}"
        )

    def test_every_transition_cell_has_matching_transition_table_entry(self) -> None:
        """Every TRANSITION cell in FULL_GUARD_TABLE for a bus topic also
        exists in the original TRANSITION_TABLE."""
        for state, topics in FULL_GUARD_TABLE.items():
            for topic, (action, tgt) in topics.items():
                if action == GuardAction.TRANSITION:
                    assert is_legal(state, topic), (
                        f"FULL_GUARD_TABLE has TRANSITION ({state.name}, {topic}) "
                        f"but TRANSITION_TABLE says illegal"
                    )

    def test_guard_action_enum_has_five_members(self) -> None:
        """GuardAction must have exactly 5 members."""
        assert len(GuardAction) == 5
        expected = {"transition", "passthrough", "observe", "queue", "dead_letter"}
        assert {a.value for a in GuardAction} == expected
        expected = {"transition", "passthrough", "observe", "queue", "dead_letter"}
        assert {a.value for a in GuardAction} == expected
