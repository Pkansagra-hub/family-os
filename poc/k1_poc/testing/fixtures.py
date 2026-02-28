"""
poc.k1_poc.testing.fixtures -- Reusable test fixture factories.

M1 E1.4.7: Provides factory functions for creating test infrastructure
with ledger support. These can be used directly or via conftest.py
pytest fixtures.

Usage::

    from poc.k1_poc.testing.fixtures import create_test_ledger, create_wired_fsm

    writer, store = create_test_ledger(session_id="test-1")
    components = create_wired_fsm(with_ledger=True)
"""

from __future__ import annotations

from typing import Any


def create_test_ledger(
    session_id: str = "test-session",
) -> tuple[Any, Any]:
    """Create a LedgerWriter + InMemoryLedgerStore pair for testing.

    Args:
        session_id: Session scope for the writer.

    Returns:
        Tuple of (LedgerWriter, InMemoryLedgerStore).
    """
    from poc.k1_poc.ledger.store import InMemoryLedgerStore
    from poc.k1_poc.ledger.writer import LedgerWriter

    store = InMemoryLedgerStore()
    writer = LedgerWriter(store=store, session_id=session_id)
    return writer, store


def create_wired_fsm(
    *,
    capture: bool = True,
    with_ledger: bool = True,
    with_dead_letter_consumer: bool = True,
    with_cancel_tokens: bool = False,
    with_arbiter: bool = True,
    session_id: str = "test-session",
    # M7 E7.5.7: BackPool + Lease + ReadyQueue + TopicRouter
    with_back_pool: bool = False,
    pool_size: int = 3,
    with_lease: bool = False,
    lease_ttl_s: float = 300.0,
    with_ready_queue: bool = False,
    with_topic_router: bool = False,
    # M8 E8.5.7: WeavePolicy + UserActivityTracker
    with_weave_policy: bool = False,
    with_activity_tracker: bool = False,
) -> dict[str, Any]:
    """Create a fully wired FSM with bus, router, and optional ledger.

    Returns a dict with keys: bus, router, fsm, and optionally
    ledger, ledger_store, dead_letter_consumer, cancel_handler, arbiter,
    back_pool, ready_queue, topic_router.

    Args:
        capture:                  If True, bus captures published envelopes.
        with_ledger:              If True, create and attach a LedgerWriter.
        with_dead_letter_consumer: If True, create DeadLetterConsumer on the bus.
        with_cancel_tokens:       If True, expose the FSM's CancellationHandler.
        with_arbiter:             If True, expose the FSM's ConversationArbiter.
        session_id:               Session ID for the ledger writer.
        with_back_pool:           M7: Create BackPool + BackPoolConfig.
        pool_size:                M7: Override default pool_size.
        with_lease:               M7: Implies with_back_pool=True.
        lease_ttl_s:              M7: Override default lease TTL.
        with_ready_queue:         M7: Create ReadyQueue for dep ordering.
        with_topic_router:        M7: Create BackTopicRouter with standard routes.
        with_weave_policy:        M8: Create WeavePolicy + implied activity_tracker.
        with_activity_tracker:    M8: Create UserActivityTracker standalone.

    Returns:
        Dict of wired components.
    """
    from poc.k1_poc.bus.setup import create_poc_bus, create_poc_router
    from poc.k1_poc.fsm.controller import ConciergeController

    # M7 E7.5.7: with_lease implies with_back_pool
    if with_lease:
        with_back_pool = True
    # M7 E7.5.7: with_topic_router implies with_back_pool
    if with_topic_router:
        with_back_pool = True
    # M7 E7.5.7: with_back_pool implies with_cancel_tokens
    if with_back_pool:
        with_cancel_tokens = True
    # M8 E8.5.7: with_weave_policy implies with_activity_tracker
    if with_weave_policy:
        with_activity_tracker = True

    bus = create_poc_bus(capture=capture)
    router = create_poc_router()
    fsm = ConciergeController(bus=bus, router=router)

    result: dict[str, Any] = {"bus": bus, "router": router, "fsm": fsm}

    if with_ledger:
        writer, store = create_test_ledger(session_id=session_id)
        fsm.set_ledger(writer)
        result["ledger"] = writer
        result["ledger_store"] = store

    if with_dead_letter_consumer:
        from poc.k1_poc.fsm.dead_letter_consumer import DeadLetterConsumer

        consumer = DeadLetterConsumer(bus=bus)
        result["dead_letter_consumer"] = consumer

    if with_cancel_tokens:
        result["cancel_handler"] = fsm._cancel_handler

    if with_arbiter:
        result["arbiter"] = fsm._arbiter

    # M7 E7.5.7: BackPool
    if with_back_pool:
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

        pool_config = BackPoolConfig(pool_size=pool_size, lease_ttl_s=lease_ttl_s)
        back_pool = BackPool(pool_config)
        fsm.set_back_pool(back_pool)
        result["back_pool"] = back_pool

    # M7 E7.5.7: ReadyQueue
    if with_ready_queue:
        from poc.k1_poc.actors.ready_queue import ReadyQueue

        ready_queue = ReadyQueue()
        result["ready_queue"] = ready_queue

    # M7 E7.5.7: BackTopicRouter
    if with_topic_router:
        from poc.k1_poc.actors.back_router import BackTopicRouter

        topic_router = BackTopicRouter(
            back_pool=result.get("back_pool"),
        )
        result["topic_router"] = topic_router

    # M8 E8.5.7: WeavePolicy
    if with_weave_policy:
        from poc.k1_poc.protocols.weave_policy import WeavePolicy

        weave_policy = WeavePolicy()
        fsm.set_weave_policy(weave_policy)
        result["weave_policy"] = weave_policy

    # M8 E8.5.7: UserActivityTracker
    if with_activity_tracker:
        from poc.k1_poc.protocols.weave_policy import UserActivityTracker

        activity_tracker = UserActivityTracker()
        fsm.set_activity_tracker(activity_tracker)
        result["activity_tracker"] = activity_tracker

    return result


def assert_ledger_contains(
    store: Any,
    event_type: str,
    *,
    count: int | None = None,
    min_count: int = 1,
    session_id: str | None = None,
) -> list[Any]:
    """Assert that the ledger store contains events of the given type.

    Args:
        store:      An InMemoryLedgerStore instance.
        event_type: Canonical event_type string to look for.
        count:      If set, assert exactly this many. Overrides min_count.
        min_count:  Assert at least this many (default 1).
        session_id: If set, filter by session. Otherwise reads all.

    Returns:
        The matching LedgerEntry list (for further assertions).
    """
    if session_id:
        entries = store.read_by_type(session_id, event_type)
    else:
        entries = [e for e in store.read_all() if e.event_type == event_type]

    if count is not None:
        assert (
            len(entries) == count
        ), f"Expected exactly {count} '{event_type}' events, found {len(entries)}"
    else:
        assert (
            len(entries) >= min_count
        ), f"Expected at least {min_count} '{event_type}' events, found {len(entries)}"
    return entries


def assert_ledger_empty(store: Any, session_id: str | None = None) -> None:
    """Assert that the ledger store has no entries."""
    total = store.count(session_id)
    assert total == 0, f"Expected empty ledger, found {total} entries"


# ---------------------------------------------------------------------------
# M2 E2.5 — Dead-letter & guard assertion helpers
# ---------------------------------------------------------------------------


def assert_dead_letter_count(
    consumer: Any,
    expected: int,
    *,
    reason: str | None = None,
) -> list[Any]:
    """Assert the dead-letter consumer holds *expected* events.

    Args:
        consumer:  DeadLetterConsumer instance.
        expected:  Exact count of dead-letter events.
        reason:    If set, filter snapshot by this reason string.

    Returns:
        The matching dead-letter event list.
    """
    all_events = consumer.events
    events = all_events if reason is None else [e for e in all_events if e.reason == reason]
    assert len(events) == expected, (
        f"Expected {expected} dead-letter events"
        f"{f' with reason={reason!r}' if reason else ''}, "
        f"found {len(events)}"
    )
    return events


def assert_dead_letter_reason(
    consumer: Any,
    reason: str,
    *,
    min_count: int = 1,
) -> list[Any]:
    """Assert at least *min_count* dead-letter events with *reason*.

    Returns:
        Matching events.
    """
    all_events = consumer.events
    matched = [e for e in all_events if e.reason == reason]
    assert len(matched) >= min_count, (
        f"Expected at least {min_count} dead-letter events with "
        f"reason={reason!r}, found {len(matched)}"
    )
    return matched


def assert_guard_action(
    store: Any,
    event_type: str,
    expected_action: str,
    *,
    session_id: str | None = None,
) -> list[Any]:
    """Assert that guard decisions in the ledger match *expected_action*.

    Looks for ledger entries of type 'conversation.guard.dispatched' whose
    payload contains the given *event_type* and verifies the action field.

    Args:
        store:           InMemoryLedgerStore.
        event_type:      The event_type that was guarded.
        expected_action: The guard action (e.g. 'allow', 'reject', 'defer').
        session_id:      Optional session filter.

    Returns:
        Matching entries.
    """
    if session_id:
        entries = store.read_by_type(session_id, "conversation.guard.dispatched")
    else:
        entries = [e for e in store.read_all() if e.event_type == "conversation.guard.dispatched"]

    matched = [
        e
        for e in entries
        if getattr(e, "payload", {}).get("event_type") == event_type
        and getattr(e, "payload", {}).get("action") == expected_action
    ]
    assert len(matched) >= 1, (
        f"Expected guard action={expected_action!r} for event_type={event_type!r}, "
        f"found {len(matched)} matches in {len(entries)} guard entries"
    )
    return matched


# ---------------------------------------------------------------------------
# M3 E3.7.6 — Cancel token and handler invocation helpers
# ---------------------------------------------------------------------------


def create_test_cancel_token(task_id: str = "test-task") -> Any:
    """Create a standalone CancellationToken for testing.

    Args:
        task_id: Task ID to bind to the token.

    Returns:
        A CancellationToken instance.
    """
    from poc.k1_poc.protocols.cancellation import CancellationToken

    return CancellationToken(task_id=task_id)


async def invoke_back_handler(
    envelope: Any,
    *,
    model: Any = None,
    ss: Any = None,
    bus: Any = None,
    tool_dispatcher: Any = None,
    fsm_state: Any = None,
    cancel_token: Any = None,
) -> Any:
    """Invoke back_handler with sensible defaults for testing.

    Wraps the back_handler function, providing None defaults for
    optional parameters so tests can focus on the behavior under test.

    Returns:
        ReactResult from back_handler.
    """
    from poc.k1_poc.actors.back import back_handler

    return await back_handler(
        envelope=envelope,
        model=model,
        ss=ss,
        bus=bus,
        tool_dispatcher=tool_dispatcher,
        fsm_state=fsm_state,
        cancel_token=cancel_token,
    )


async def invoke_back_router(
    envelope: Any,
    *,
    model: Any = None,
    ss: Any = None,
    bus: Any = None,
    tool_dispatcher: Any = None,
    fsm_state: Any = None,
) -> Any:
    """Invoke route_back_envelope with sensible defaults for testing.

    Wraps route_back_envelope, providing None defaults for optional
    parameters so tests can focus on routing behavior.

    Returns:
        ReactResult from the routed handler, or None.
    """
    from poc.k1_poc.actors.back import route_back_envelope

    return await route_back_envelope(
        envelope=envelope,
        model=model,
        ss=ss,
        bus=bus,
        tool_dispatcher=tool_dispatcher,
        fsm_state=fsm_state,
    )


# ---------------------------------------------------------------------------
# M4 E4.5.7 -- SessionState binding and writer port helpers
# ---------------------------------------------------------------------------


def create_wired_fsm_with_ss(
    *,
    capture: bool = True,
    with_ledger: bool = True,
    with_dead_letter_consumer: bool = True,
    with_ss_binding: bool = True,
    with_writer_port: bool = True,
    with_arbiter: bool = True,
    session_id: str = "test-session",
) -> dict[str, Any]:
    """Create a fully wired FSM with SessionState + M4 binding.

    Extends create_wired_fsm with:
      - Real SessionStateManager (with_ss_binding)
      - DirectWriterAdapter wired into ToolContext (with_writer_port)
      - TaskBridge rebind + ControlExtension bind via set_session_state
      - ConversationArbiter exposure (with_arbiter)

    Args:
        capture:                   If True, bus captures published envelopes.
        with_ledger:               If True, create and attach a LedgerWriter.
        with_dead_letter_consumer: If True, create DeadLetterConsumer.
        with_ss_binding:           If True, create SS and call set_session_state.
        with_writer_port:          If True, create DirectWriterAdapter.
        with_arbiter:              If True, expose the FSM's ConversationArbiter.
        session_id:                Session ID for the ledger writer.

    Returns:
        Dict with keys: bus, router, fsm, and optionally
        ledger, ledger_store, dead_letter_consumer, session_state,
        writer_port, front_ctx, back_ctx, arbiter.
    """
    result = create_wired_fsm(
        capture=capture,
        with_ledger=with_ledger,
        with_dead_letter_consumer=with_dead_letter_consumer,
        with_arbiter=with_arbiter,
        session_id=session_id,
    )

    if with_ss_binding:
        from poc.k1_poc.sessionstate.factory import SessionStateFactory

        ss = SessionStateFactory.create_for_testing(session_id=session_id)
        ss.start()
        result["session_state"] = ss
        result["fsm"].set_session_state(ss)

    if with_writer_port:
        ss = result.get("session_state")
        if ss is None:
            from poc.k1_poc.sessionstate.factory import SessionStateFactory

            ss = SessionStateFactory.create_for_testing(session_id=session_id)
            ss.start()
            result["session_state"] = ss

        from poc.k1_poc.sessionstate.adapters.direct_writer import DirectWriterAdapter

        writer = DirectWriterAdapter(
            manager=ss,
            guard=ss.mutation_guard,
            writer_id="test",
        )
        result["writer_port"] = writer

    return result


def create_test_tool_context(
    *,
    session_state: Any = None,
    writer_port: Any = None,
    actor: str = "front",
    trace_id: str = "trace-test",
) -> Any:
    """Create a ToolContext with optional writer_port for testing.

    Args:
        session_state: SessionStateManager (creates one if None).
        writer_port: IWriterPort (creates DirectWriterAdapter if None
                     and session_state is provided).
        actor: Actor identity ("front" or "back").
        trace_id: Cognitive trace ID.

    Returns:
        ToolContext instance.
    """
    from poc.k1_poc.tools.implementations import ToolContext

    if session_state is None:
        from poc.k1_poc.sessionstate.factory import SessionStateFactory

        session_state = SessionStateFactory.create_for_testing()
        session_state.start()

    if writer_port is None:
        from poc.k1_poc.sessionstate.adapters.direct_writer import DirectWriterAdapter

        writer_port = DirectWriterAdapter(
            manager=session_state,
            guard=session_state.mutation_guard,
            writer_id="test",
        )

    return ToolContext(
        session_manager=session_state,
        cognitive_trace_id=trace_id,
        actor=actor,
        writer_port=writer_port,
    )


def assert_mutation_approved(response: Any) -> None:
    """Assert that a MutationResponse was approved.

    Args:
        response: MutationResponse from writer_port.request_mutation().

    Raises:
        AssertionError with details if not approved.
    """
    from poc.k1_poc.sessionstate.ports.writer import MutationStatus

    assert response.status == MutationStatus.APPLIED, (
        f"Expected mutation APPLIED, got {response.status.value}: "
        f"section={response.section}, reason={getattr(response, 'reason', 'N/A')}"
    )


def assert_mutation_rejected(
    response: Any,
    *,
    category: str | None = None,
) -> None:
    """Assert that a MutationResponse was rejected.

    Args:
        response: MutationResponse from writer_port.request_mutation().
        category: If set, also assert the rejection category matches.

    Raises:
        AssertionError with details if not rejected.
    """
    from poc.k1_poc.sessionstate.ports.writer import MutationStatus

    assert response.status == MutationStatus.REJECTED, (
        f"Expected mutation REJECTED, got {response.status.value}: " f"section={response.section}"
    )
    if category is not None:
        actual = getattr(response, "rejection_category", None)
        actual_val = actual.value if actual else None
        assert actual_val == category, f"Expected rejection category={category}, got {actual_val}"


# ---------------------------------------------------------------------------
# M5 E5.5.7 -- Arbiter test helpers
# ---------------------------------------------------------------------------


def create_test_arbiter(
    *,
    domain_overlap_threshold: float = 0.7,
    entity_overlap_threshold: float = 0.5,
) -> Any:
    """Create a ConversationArbiter with configurable thresholds.

    Args:
        domain_overlap_threshold: Threshold for domain overlap classification.
        entity_overlap_threshold: Threshold for entity overlap classification.

    Returns:
        ConversationArbiter instance.
    """
    from poc.k1_poc.fsm.arbiter import ArbiterConfig, ConversationArbiter

    config = ArbiterConfig(
        domain_overlap_threshold=domain_overlap_threshold,
        entity_overlap_threshold=entity_overlap_threshold,
    )
    return ConversationArbiter(config=config)


def create_test_inflight_context(
    *,
    tasks: list[Any] | None = None,
    fsm_state: str = "COMPANIONING",
    pending_results: int = 0,
    device_id: str | None = None,
    cancelled_task_ids: set[str] | None = None,
    current_turn: int = 1,
) -> Any:
    """Create an InflightContext for arbiter test scenarios.

    Args:
        tasks:              List of InflightTask objects (or empty).
        fsm_state:          FSM state string.
        pending_results:    Count of pending results.
        device_id:          Active device ID.
        cancelled_task_ids: Set of cancelled task IDs.
        current_turn:       Current turn number.

    Returns:
        InflightContext instance.
    """
    from poc.k1_poc.fsm.arbiter import InflightContext

    return InflightContext(
        tasks=tasks or [],
        pending_results=pending_results,
        cancelled_task_ids=cancelled_task_ids or set(),
        fsm_state=fsm_state,
        current_turn=current_turn,
        active_device_id=device_id,
    )


def create_test_inflight_task(
    *,
    task_id: str = "task-1",
    action: str = "search",
    domain: str = "travel",
    entities: list[str] | None = None,
    status: str = "in_progress",
    progress_pct: float = 0.0,
    dispatch_turn: int = 1,
    pending_hil: bool = False,
) -> Any:
    """Create an InflightTask for arbiter test scenarios.

    Args:
        task_id: Task identifier.
        action:  Task action.
        domain:  Task domain.
        entities: List of entity strings.
        status:  Task status.
        progress_pct: Task progress percentage.
        dispatch_turn: Turn when task was dispatched.
        pending_hil: Whether task is pending HIL.

    Returns:
        InflightTask instance.
    """
    from poc.k1_poc.fsm.arbiter import InflightTask

    return InflightTask(
        task_id=task_id,
        action=action,
        domain=domain,
        entities=entities or [],
        status=status,
        progress_pct=progress_pct,
        dispatch_turn=dispatch_turn,
        pending_hil=pending_hil,
    )


def assert_arbiter_decision(result: Any, expected_decision: str) -> None:
    """Assert that an ArbiterResult has the expected decision.

    Args:
        result: ArbiterResult from ConversationArbiter.classify().
        expected_decision: Expected ArbiterDecision value string
            (e.g. "PARALLEL_NEW", "CANCEL", "MODIFY_INFLIGHT", "DEFER").

    Raises:
        AssertionError if decision doesn't match.
    """
    actual = result.decision.value
    assert (
        actual == expected_decision
    ), f"Expected Arbiter decision {expected_decision!r}, got {actual!r}"


def assert_ledger_has_intent_arbitrated(
    store: Any,
    decision: str | None = None,
    *,
    min_count: int = 1,
) -> list[Any]:
    """Assert that the ledger has IntentArbitrated events.

    Args:
        store: InMemoryLedgerStore.
        decision: If set, only count events with this decision value.
        min_count: Minimum number of matching events.

    Returns:
        List of matching ledger entries.
    """
    entries = [e for e in store.read_all() if e.event_type == "conversation.intent.arbitrated"]
    if decision is not None:
        entries = [e for e in entries if getattr(e, "payload", {}).get("decision") == decision]
    label = f"IntentArbitrated({decision})" if decision else "IntentArbitrated"
    assert (
        len(entries) >= min_count
    ), f"Expected at least {min_count} {label} in ledger, found {len(entries)}"
    return entries


# ---------------------------------------------------------------------------
# M6 E6.5.7 -- HITL wiring test helpers
# ---------------------------------------------------------------------------


def create_wired_fsm_with_hitl(
    *,
    capture: bool = True,
    with_ledger: bool = True,
    with_dead_letter_consumer: bool = True,
    with_ss_binding: bool = True,
    with_arbiter: bool = True,
    max_rounds: int = 2,
    timeout_clarification: float = 5.0,
    session_id: str = "test-session",
) -> dict[str, Any]:
    """Create a fully wired FSM with HILCoordinator and SS binding.

    Extends create_wired_fsm_with_ss with HITL wiring:
      - HILCoordinator with test config
      - set_hitl_coordinator called on FSM
      - SS binding for crash recovery

    Args:
        capture:                  If True, bus captures published envelopes.
        with_ledger:              If True, create and attach a LedgerWriter.
        with_dead_letter_consumer: If True, create DeadLetterConsumer.
        with_ss_binding:          If True, create SS and call set_session_state.
        with_arbiter:             If True, expose the FSM's ConversationArbiter.
        max_rounds:               Max HITL rounds per task.
        timeout_clarification:    Clarification timeout in seconds.
        session_id:               Session ID for the ledger writer.

    Returns:
        Dict with keys: bus, router, fsm, hil_coordinator, and optionally
        ledger, ledger_store, dead_letter_consumer, session_state, arbiter.
    """
    result = create_wired_fsm_with_ss(
        capture=capture,
        with_ledger=with_ledger,
        with_dead_letter_consumer=with_dead_letter_consumer,
        with_ss_binding=with_ss_binding,
        with_writer_port=False,
        with_arbiter=with_arbiter,
        session_id=session_id,
    )

    coordinator = create_test_hil_coordinator(
        max_rounds=max_rounds,
        timeout_clarification=timeout_clarification,
    )
    result["fsm"].set_hitl_coordinator(coordinator)
    result["hil_coordinator"] = coordinator
    return result


def create_test_hil_coordinator(
    *,
    max_rounds: int = 2,
    timeout_clarification: float = 5.0,
    timeout_approval: float = 10.0,
    timeout_selection: float = 7.5,
    block_red: bool = True,
    auto_escalate_side_effects: bool = True,
) -> Any:
    """Create an HILCoordinator with test configuration.

    Args:
        max_rounds: Max HITL rounds per task.
        timeout_clarification: Clarification timeout in seconds.
        timeout_approval: Approval timeout in seconds.
        timeout_selection: Selection timeout in seconds.
        block_red: Whether to block RED safety band.
        auto_escalate_side_effects: Whether GREEN+side_effects -> AMBER.

    Returns:
        HILCoordinator instance.
    """
    from poc.k1_poc.protocols.hitl_coordinator import HILCoordinator, HILCoordinatorConfig

    config = HILCoordinatorConfig(
        max_rounds=max_rounds,
        timeouts={
            "clarification": timeout_clarification,
            "approval": timeout_approval,
            "selection": timeout_selection,
        },
        block_red=block_red,
        auto_escalate_side_effects=auto_escalate_side_effects,
    )
    return HILCoordinator(config=config)


def create_test_hil_subtask(
    *,
    task_id: str = "test-task-1",
    hil_type: str = "clarification",
    question: str = "What cuisine do you prefer?",
    options: list[str] | None = None,
    safety_band: str = "GREEN",
    timeout_ms: int = 5000,
    resume_token: str | None = None,
    react_snapshot: dict | None = None,
    device_id: str = "device-1",
) -> Any:
    """Create an HILSubTask for testing.

    Args:
        task_id: Parent task ID.
        hil_type: Type of HITL request.
        question: HITL question text.
        options: Options for selection type.
        safety_band: Safety classification.
        timeout_ms: Timeout in milliseconds.
        resume_token: Custom resume token (auto-generated if None).
        react_snapshot: ReAct snapshot dict (default empty).
        device_id: Device ID.

    Returns:
        HILSubTask instance.
    """
    from poc.k1_poc.protocols.hitl_persistence import HILSubTask

    kwargs: dict = dict(
        hil_type=hil_type,
        parent_task_id=task_id,
        question=question,
        options=options or [],
        safety_band=safety_band,
        timeout_ms=timeout_ms,
        react_snapshot=react_snapshot
        or {
            "prior_messages": [],
            "tool_history": [],
            "last_iteration": 0,
        },
        device_id=device_id,
    )
    if resume_token is not None:
        kwargs["resume_token"] = resume_token
    return HILSubTask(**kwargs)


def assert_hitl_lifecycle_in_ledger(
    store: Any,
    task_id: str,
    expected_types: list[str],
    *,
    session_id: str | None = None,
) -> list[Any]:
    """Assert HITL lifecycle events appear in ledger in order.

    Args:
        store: InMemoryLedgerStore instance.
        task_id: Task ID to filter by.
        expected_types: Ordered list of event_type strings, e.g.
            ["hitl.requested.v1", "hitl.resolved.v1"].
        session_id: Optional session filter.

    Returns:
        Matching ledger entries in order.

    Raises:
        AssertionError if events are missing or out of order.
    """
    if session_id:
        all_entries = store.read_all_for_session(session_id)
    else:
        all_entries = store.read_all()

    # Filter to HITL events for this task
    hitl_entries = [
        e
        for e in all_entries
        if getattr(e, "event_type", "") in expected_types
        and (getattr(e, "payload", {}) or {}).get("task_id") == task_id
    ]

    found_types = [e.event_type for e in hitl_entries]
    for expected in expected_types:
        assert expected in found_types, (
            f"Expected HITL lifecycle event '{expected}' for task {task_id} "
            f"in ledger, found: {found_types}"
        )

    # Verify ordering
    for i, expected in enumerate(expected_types):
        idx = found_types.index(expected)
        if i > 0:
            prev_idx = found_types.index(expected_types[i - 1])
            assert idx > prev_idx, (
                f"HITL lifecycle event '{expected}' should appear after "
                f"'{expected_types[i - 1]}' but found at index {idx} vs {prev_idx}"
            )
    return hitl_entries


def assert_no_hitl_dead_letters(consumer: Any) -> None:
    """Assert no HITL topics ended up in dead-letter queue.

    Args:
        consumer: DeadLetterConsumer instance.

    Raises:
        AssertionError if any HITL dead-letter events found.
    """
    hitl_topics = {
        "k1.hitl.requested.v1",
        "k1.hitl.resolved.v1",
        "k1.hitl.timed_out.v1",
        "k1.hitl.blocked_red.v1",
    }
    events = consumer.events
    hitl_dls = [e for e in events if getattr(e, "topic", "") in hitl_topics]
    assert len(hitl_dls) == 0, (
        f"Found {len(hitl_dls)} HITL dead-letter events: "
        f"{[getattr(e, 'topic', '') for e in hitl_dls]}"
    )


# ---------------------------------------------------------------------------
# M7 E7.1 -- BackPool test helpers
# ---------------------------------------------------------------------------


def create_test_back_pool(
    *,
    pool_size: int = 3,
    max_concurrent_per_session: int = 2,
    lease_ttl_s: float = 300.0,
    on_worker_acquired: Any = None,
    on_worker_released: Any = None,
) -> Any:
    """Create a BackPool with test configuration.

    Args:
        pool_size: Maximum concurrent workers.
        max_concurrent_per_session: Per-session concurrency limit.
        lease_ttl_s: Default lease TTL.
        on_worker_acquired: Optional callback for worker acquisition.
        on_worker_released: Optional callback for worker release.

    Returns:
        BackPool instance.
    """
    from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

    config = BackPoolConfig(
        pool_size=pool_size,
        max_concurrent_per_session=max_concurrent_per_session,
        lease_ttl_s=lease_ttl_s,
    )
    return BackPool(
        config,
        on_worker_acquired=on_worker_acquired,
        on_worker_released=on_worker_released,
    )


def create_test_worker_slot(
    *,
    task_id: str = "test-task-1",
    session_id: str | None = "test-session",
) -> Any:
    """Create a standalone WorkerSlot for testing.

    Args:
        task_id: Task ID for the worker.
        session_id: Session ID for concurrency tracking.

    Returns:
        WorkerSlot instance.
    """
    from poc.k1_poc.actors.back_pool import WorkerSlot

    return WorkerSlot(task_id=task_id, session_id=session_id)


def assert_pool_state(
    pool: Any,
    *,
    active: int | None = None,
    available: int | None = None,
    overflow: int | None = None,
) -> None:
    """Assert BackPool state matches expected values.

    Args:
        pool: BackPool instance.
        active: Expected number of active workers.
        available: Expected number of available slots.
        overflow: Expected overflow queue depth.

    Raises:
        AssertionError if any value doesn't match.
    """
    state = pool.get_pool_state()
    if active is not None:
        assert state["active"] == active, f"Expected {active} active workers, got {state['active']}"
    if available is not None:
        assert (
            state["available"] == available
        ), f"Expected {available} available slots, got {state['available']}"
    if overflow is not None:
        assert (
            state["overflow"] == overflow
        ), f"Expected {overflow} overflow envelopes, got {state['overflow']}"


# =====================================================================
# M7 E7.2 -- Task Lease helpers
# =====================================================================


def create_test_task_lease(
    *,
    task_id: str = "test-task-1",
    worker_id: str = "test-worker-1",
    lease_ttl_s: float = 300.0,
    max_renewals: int = 3,
) -> Any:
    """Create a TaskLease for testing.

    Args:
        task_id: Task ID for the lease.
        worker_id: Worker ID for the lease.
        lease_ttl_s: Lease duration in seconds.
        max_renewals: Maximum allowed renewals.

    Returns:
        TaskLease instance.
    """
    from poc.k1_poc.protocols.task_lease import create_task_lease

    return create_task_lease(
        task_id=task_id,
        worker_id=worker_id,
        lease_ttl_s=lease_ttl_s,
        max_renewals=max_renewals,
    )


def create_test_expired_lease(
    *,
    task_id: str = "expired-task-1",
    worker_id: str = "expired-worker-1",
) -> Any:
    """Create a TaskLease that is already expired (TTL = 0).

    Returns:
        TaskLease with expires_at_ns in the past.
    """
    import time

    from poc.k1_poc.protocols.cancellation import CancellationToken
    from poc.k1_poc.protocols.task_lease import TaskLease

    lease = TaskLease(
        task_id=task_id,
        worker_id=worker_id,
        granted_at_ns=time.monotonic_ns() - int(1e9),  # 1s ago
        expires_at_ns=time.monotonic_ns() - int(0.5e9),  # 0.5s ago
        cancellation_token=CancellationToken(task_id=task_id),
    )
    return lease


def assert_lease_state(
    lease: Any,
    *,
    status: str | None = None,
    is_expired: bool | None = None,
    renewed_count: int | None = None,
) -> None:
    """Assert TaskLease state matches expected values.

    Args:
        lease: TaskLease instance.
        status: Expected status value string.
        is_expired: Expected expiry state.
        renewed_count: Expected renewal count.

    Raises:
        AssertionError if any value doesn't match.
    """
    if status is not None:
        assert (
            lease.status.value == status
        ), f"Expected lease status '{status}', got '{lease.status.value}'"
    if is_expired is not None:
        assert (
            lease.is_expired == is_expired
        ), f"Expected is_expired={is_expired}, got {lease.is_expired}"
    if renewed_count is not None:
        assert (
            lease.renewed_count == renewed_count
        ), f"Expected renewed_count={renewed_count}, got {lease.renewed_count}"


# =====================================================================
# M7 E7.3 -- BackTopicRouter test helpers
# =====================================================================


def create_test_back_topic_router(
    back_pool: Any = None,
) -> Any:
    """Create a BackTopicRouter for testing.

    M7 E7.3: Returns a configured router with optional pool attachment.

    Args:
        back_pool: Optional BackPool for late-envelope discard checks.

    Returns:
        BackTopicRouter instance.
    """
    from poc.k1_poc.actors.back_router import BackTopicRouter

    return BackTopicRouter(back_pool=back_pool)


def assert_router_stats(
    router: Any,
    *,
    routed: int | None = None,
    cancel_sync: int | None = None,
    discarded_late: int | None = None,
    discarded_unknown: int | None = None,
) -> None:
    """Assert BackTopicRouter routing statistics.

    Args:
        router: BackTopicRouter instance.
        routed: Expected total routed count.
        cancel_sync: Expected cancel-sync count.
        discarded_late: Expected late-discard count.
        discarded_unknown: Expected unknown-topic discard count.

    Raises:
        AssertionError if any value doesn't match.
    """
    stats = router.get_stats()
    if routed is not None:
        assert stats["routed"] == routed, f"Expected routed={routed}, got {stats['routed']}"
    if cancel_sync is not None:
        assert (
            stats["cancel_sync"] == cancel_sync
        ), f"Expected cancel_sync={cancel_sync}, got {stats['cancel_sync']}"
    if discarded_late is not None:
        assert (
            stats["discarded_late"] == discarded_late
        ), f"Expected discarded_late={discarded_late}, got {stats['discarded_late']}"
    if discarded_unknown is not None:
        assert stats["discarded_unknown"] == discarded_unknown, (
            f"Expected discarded_unknown={discarded_unknown}, " f"got {stats['discarded_unknown']}"
        )


# =====================================================================
# M7 E7.4 -- ReadyQueue test helpers
# =====================================================================


def create_test_ready_queue() -> Any:
    """Create a ReadyQueue for testing.

    M7 E7.4: Returns a fresh ReadyQueue instance.

    Returns:
        ReadyQueue instance.
    """
    from poc.k1_poc.actors.ready_queue import ReadyQueue

    return ReadyQueue()


def assert_ready_queue_state(
    queue: Any,
    *,
    ready: int | None = None,
    waiting: int | None = None,
) -> None:
    """Assert ReadyQueue state matches expected values.

    Args:
        queue: ReadyQueue instance.
        ready: Expected number of ready envelopes.
        waiting: Expected number of waiting envelopes.

    Raises:
        AssertionError if any value doesn't match.
    """
    if ready is not None:
        assert (
            queue.ready_count == ready
        ), f"Expected {ready} ready envelopes, got {queue.ready_count}"
    if waiting is not None:
        assert (
            queue.waiting_count == waiting
        ), f"Expected {waiting} waiting envelopes, got {queue.waiting_count}"


def assert_queue_stats(
    queue: Any,
    *,
    immediate: int | None = None,
    enqueued: int | None = None,
    released: int | None = None,
    failed_dep: int | None = None,
    circular: int | None = None,
    unknown_dep: int | None = None,
) -> None:
    """Assert ReadyQueue routing statistics.

    Args:
        queue: ReadyQueue instance.
        immediate: Expected immediate dispatch count.
        enqueued: Expected enqueued (waiting) count.
        released: Expected released (dependency met) count.
        failed_dep: Expected dependency-failed count.
        circular: Expected circular dependency count.
        unknown_dep: Expected unknown dependency count.

    Raises:
        AssertionError if any value doesn't match.
    """
    stats = queue.get_stats()
    if immediate is not None:
        assert (
            stats["immediate"] == immediate
        ), f"Expected immediate={immediate}, got {stats['immediate']}"
    if enqueued is not None:
        assert (
            stats["enqueued"] == enqueued
        ), f"Expected enqueued={enqueued}, got {stats['enqueued']}"
    if released is not None:
        assert (
            stats["released"] == released
        ), f"Expected released={released}, got {stats['released']}"
    if failed_dep is not None:
        assert (
            stats["failed_dep"] == failed_dep
        ), f"Expected failed_dep={failed_dep}, got {stats['failed_dep']}"
    if circular is not None:
        assert (
            stats["circular"] == circular
        ), f"Expected circular={circular}, got {stats['circular']}"
    if unknown_dep is not None:
        assert (
            stats["unknown_dep"] == unknown_dep
        ), f"Expected unknown_dep={unknown_dep}, got {stats['unknown_dep']}"


__all__ = [
    "create_test_ledger",
    "create_wired_fsm",
    "create_wired_fsm_with_ss",
    "create_test_tool_context",
    "assert_ledger_contains",
    "assert_ledger_empty",
    "assert_dead_letter_count",
    "assert_dead_letter_reason",
    "assert_guard_action",
    "assert_mutation_approved",
    "assert_mutation_rejected",
    "create_test_cancel_token",
    "invoke_back_handler",
    "invoke_back_router",
    # M5 E5.5.7
    "create_test_arbiter",
    "create_test_inflight_context",
    "create_test_inflight_task",
    "assert_arbiter_decision",
    "assert_ledger_has_intent_arbitrated",
    # M6 E6.5.7
    "create_wired_fsm_with_hitl",
    "create_test_hil_subtask",
    "create_test_hil_coordinator",
    "assert_hitl_lifecycle_in_ledger",
    "assert_no_hitl_dead_letters",
    # M7 E7.1
    "create_test_back_pool",
    "create_test_worker_slot",
    "assert_pool_state",
    # M7 E7.2
    "create_test_task_lease",
    "create_test_expired_lease",
    "assert_lease_state",
    # M7 E7.3
    "create_test_back_topic_router",
    "assert_router_stats",
    # M7 E7.4
    "create_test_ready_queue",
    "assert_ready_queue_state",
    "assert_queue_stats",
]
