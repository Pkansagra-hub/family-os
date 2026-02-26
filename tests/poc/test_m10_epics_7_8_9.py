"""
Tests for Epics 10.7, 10.8, 10.9 -- dispatch_task tool, TaskReceiver,
BundledExecutionPlan.

Epic 10.7: dispatch_task async tool + DISPATCH_TASK_SCHEMA
Epic 10.8: TaskReceiver with dependency routing and chained execution
Epic 10.9: IntentResult, BundledExecutionPlan for bundled intent tracking

Source of truth: implemented code + concierge_poc_design_v2.md Sections 6.1, 6.2, 8.4
"""

from __future__ import annotations

import pytest

from poc.k1_poc.task.bundled_executor import BundledExecutionPlan, IntentResult
from poc.k1_poc.task.complexity import ComplexityTier
from poc.k1_poc.task.dispatch import TaskComplete, TaskDispatch, TaskFailed
from poc.k1_poc.task.intent import TaskIntent
from poc.k1_poc.task.receiver import TaskReceiver
from poc.k1_poc.task.tools import DISPATCH_TASK_SCHEMA, dispatch_task

# =========================================================================
# Helpers
# =========================================================================


def _intent(
    action: str = "test_action",
    params: dict | None = None,
    domain: str | None = None,
    urgency: str = "normal",
) -> TaskIntent:
    return TaskIntent(
        action=action,
        params=params or {},
        domain=domain,
        urgency=urgency,
    )


def _dispatch(
    intents: list[TaskIntent] | None = None,
    tier: ComplexityTier = ComplexityTier.LOW,
    task_id: str | None = None,
    depends_on: str | None = None,
) -> TaskDispatch:
    if intents is None:
        intents = [_intent()]
    kwargs: dict = {"intents": intents, "tier": tier}
    if task_id is not None:
        kwargs["task_id"] = task_id
    if depends_on is not None:
        kwargs["depends_on"] = depends_on
    return TaskDispatch(**kwargs)


def _complete(
    task_id: str = "task-done",
    results: list[dict] | None = None,
    final_answer: str = "done",
    tool_calls: int = 1,
) -> TaskComplete:
    return TaskComplete(
        task_id=task_id,
        final_answer=final_answer,
        results=results if results is not None else [{"answer": "42"}],
        tool_calls=tool_calls,
    )


# =========================================================================
# Epic 10.7 -- dispatch_task tool function
# =========================================================================


class TestDispatchTaskSingle:
    """10.7.1 -- dispatch_task with single intent."""

    @pytest.mark.asyncio
    async def test_single_intent_returns_single_classification(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        result = await dispatch_task(
            intents_raw=[{"action": "weather", "params": {"date": "tomorrow"}}],
            tier="low",
            publish_fn=mock_publish,
        )
        assert result["classification"] == "single"
        assert result["count"] == 1
        assert len(result["dispatched"]) == 1
        assert len(published) == 1

    @pytest.mark.asyncio
    async def test_single_intent_action_preserved(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        await dispatch_task(
            intents_raw=[{"action": "search hotels", "params": {"city": "Napa"}}],
            publish_fn=mock_publish,
        )
        assert published[0].intents[0].action == "search hotels"
        assert published[0].intents[0].params == {"city": "Napa"}

    @pytest.mark.asyncio
    async def test_tier_case_insensitive(self):
        """tier parameter is case-insensitive."""
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        await dispatch_task(
            intents_raw=[{"action": "test"}],
            tier="high",
            publish_fn=mock_publish,
        )
        assert published[0].tier == ComplexityTier.HIGH

        published.clear()
        await dispatch_task(
            intents_raw=[{"action": "test"}],
            tier="HIGH",
            publish_fn=mock_publish,
        )
        assert published[0].tier == ComplexityTier.HIGH

    @pytest.mark.asyncio
    async def test_no_publish_fn_still_returns(self):
        """Works without publish_fn (testing mode)."""
        result = await dispatch_task(
            intents_raw=[{"action": "test"}],
            publish_fn=None,
        )
        assert result["count"] == 1
        assert len(result["dispatched"]) == 1

    @pytest.mark.asyncio
    async def test_reference_context_propagated(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        ref_ctx = {"the hotel": "Vineyard Inn"}
        await dispatch_task(
            intents_raw=[{"action": "book"}],
            reference_context=ref_ctx,
            publish_fn=mock_publish,
        )
        assert published[0].reference_context == ref_ctx

    @pytest.mark.asyncio
    async def test_safety_band_propagated(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        await dispatch_task(
            intents_raw=[{"action": "book"}],
            safety_band="RED",
            publish_fn=mock_publish,
        )
        assert published[0].safety_band == "RED"

    @pytest.mark.asyncio
    async def test_context_snapshot_propagated(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        snap = {"prefs": {"cuisine": "Italian"}}
        await dispatch_task(
            intents_raw=[{"action": "search"}],
            context_snapshot=snap,
            publish_fn=mock_publish,
        )
        assert published[0].context_snapshot == snap


class TestDispatchTaskBundled:
    """10.7.2 -- dispatch_task with bundled intents."""

    @pytest.mark.asyncio
    async def test_bundled_classification(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        result = await dispatch_task(
            intents_raw=[
                {"action": "book hotel", "params": {"hotel": "Vineyard Inn"}},
                {"action": "search restaurants", "params": {"near": "Vineyard Inn"}},
            ],
            tier="medium",
            publish_fn=mock_publish,
        )
        assert result["classification"] == "bundled"
        assert result["count"] == 1
        assert len(published) == 1
        assert len(published[0].intents) == 2

    @pytest.mark.asyncio
    async def test_bundled_three_intents(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        result = await dispatch_task(
            intents_raw=[
                {"action": "a1"},
                {"action": "a2"},
                {"action": "a3"},
            ],
            publish_fn=mock_publish,
        )
        assert result["classification"] == "bundled"
        assert len(published[0].intents) == 3


class TestDispatchTaskChained:
    """10.7.3 -- dispatch_task with chained intents."""

    @pytest.mark.asyncio
    async def test_chained_via_ref_params(self):
        """Intents with $ref params are classified as chained."""
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        result = await dispatch_task(
            intents_raw=[
                {"action": "book hotel", "params": {"hotel": "Vineyard Inn"}},
                {"action": "find restaurants", "params": {"near": "$prev.result.address"}},
            ],
            tier="medium",
            publish_fn=mock_publish,
        )
        assert result["classification"] == "chained"
        assert result["count"] == 2
        assert len(published) == 2
        assert published[0].depends_on is None
        assert published[1].depends_on == published[0].task_id

    @pytest.mark.asyncio
    async def test_chained_via_explicit_depends_on(self):
        """External depends_on parameter (multi-call chaining per design doc Example 3)."""
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        result = await dispatch_task(
            intents_raw=[
                {"action": "find restaurants", "params": {"near": "$prev.result.address"}},
            ],
            depends_on="task-a7f3",
            publish_fn=mock_publish,
        )
        assert result["classification"] == "chained"
        assert published[0].depends_on == "task-a7f3"


class TestDispatchTaskUrgency:
    """10.7.4 -- dispatch-level urgency application."""

    @pytest.mark.asyncio
    async def test_urgency_applied_to_intents(self):
        """Dispatch-level urgency propagates to intents without their own."""
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        await dispatch_task(
            intents_raw=[{"action": "test"}],
            urgency="urgent",
            publish_fn=mock_publish,
        )
        assert published[0].intents[0].urgency == "urgent"

    @pytest.mark.asyncio
    async def test_intent_urgency_preserved_if_specified(self):
        """If intent has its own urgency, dispatch-level does not override."""
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        await dispatch_task(
            intents_raw=[{"action": "test", "urgency": "background"}],
            urgency="urgent",
            publish_fn=mock_publish,
        )
        assert published[0].intents[0].urgency == "background"

    @pytest.mark.asyncio
    async def test_domain_propagated(self):
        published: list[TaskDispatch] = []

        async def mock_publish(td: TaskDispatch) -> None:
            published.append(td)

        await dispatch_task(
            intents_raw=[{"action": "book", "domain": "travel"}],
            publish_fn=mock_publish,
        )
        assert published[0].intents[0].domain == "travel"


# =========================================================================
# Epic 10.7 -- DISPATCH_TASK_SCHEMA
# =========================================================================


class TestDispatchTaskSchema:
    """10.7.5 -- DISPATCH_TASK_SCHEMA structure for LLM injection."""

    def test_schema_is_function_type(self):
        assert DISPATCH_TASK_SCHEMA["type"] == "function"

    def test_function_name(self):
        assert DISPATCH_TASK_SCHEMA["function"]["name"] == "dispatch_task"

    def test_has_description(self):
        desc = DISPATCH_TASK_SCHEMA["function"]["description"]
        assert isinstance(desc, str)
        assert len(desc) > 50

    def test_intents_required(self):
        params = DISPATCH_TASK_SCHEMA["function"]["parameters"]
        assert "intents" in params["required"]

    def test_intents_is_array(self):
        props = DISPATCH_TASK_SCHEMA["function"]["parameters"]["properties"]
        assert props["intents"]["type"] == "array"
        assert props["intents"]["minItems"] == 1

    def test_intent_item_has_action_required(self):
        items = DISPATCH_TASK_SCHEMA["function"]["parameters"]["properties"]["intents"]["items"]
        assert "action" in items["required"]

    def test_urgency_enum(self):
        props = DISPATCH_TASK_SCHEMA["function"]["parameters"]["properties"]
        assert props["urgency"]["enum"] == ["normal", "urgent", "background"]

    def test_reference_context_present(self):
        props = DISPATCH_TASK_SCHEMA["function"]["parameters"]["properties"]
        assert "reference_context" in props

    def test_depends_on_present(self):
        props = DISPATCH_TASK_SCHEMA["function"]["parameters"]["properties"]
        assert "depends_on" in props


# =========================================================================
# Epic 10.8 -- TaskReceiver construction
# =========================================================================


class TestTaskReceiverConstruction:
    """10.8.1 -- TaskReceiver initialization and properties."""

    def test_empty_receiver(self):
        recv = TaskReceiver()
        assert recv.active_count == 0
        assert recv.waiting_count == 0
        assert recv.completed_count == 0
        assert recv.failed_count == 0

    def test_execute_fn_default_none(self):
        recv = TaskReceiver()
        assert recv.execute_fn is None

    def test_set_execute_fn(self):
        recv = TaskReceiver()

        async def fake(td: TaskDispatch) -> TaskComplete:
            return _complete(task_id=td.task_id)

        recv.set_execute_fn(fake)
        assert recv.execute_fn is not None

    def test_has_dependency_queue(self):
        recv = TaskReceiver()
        assert recv.dependency_queue is not None


# =========================================================================
# Epic 10.8 -- TaskReceiver immediate execution
# =========================================================================


class TestTaskReceiverImmediate:
    """10.8.2 -- TaskReceiver immediate (non-chained) execution."""

    @pytest.mark.asyncio
    async def test_executes_independent_task(self):
        executed: list[str] = []

        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            executed.append(td.task_id)
            return _complete(task_id=td.task_id)

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)
        await recv.handle(_dispatch())

        assert len(executed) == 1
        assert recv.completed_count == 1
        assert recv.active_count == 0

    @pytest.mark.asyncio
    async def test_bundled_dispatch_executes_once(self):
        """Bundled dispatch (multiple intents) executes as one task."""
        executed: list[str] = []

        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            executed.append(td.task_id)
            return _complete(task_id=td.task_id)

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)

        td = _dispatch(intents=[_intent(action="a1"), _intent(action="a2")])
        await recv.handle(td)

        assert len(executed) == 1
        assert recv.completed_count == 1

    @pytest.mark.asyncio
    async def test_result_stored(self):
        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            return _complete(task_id=td.task_id, results=[{"val": 42}])

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)
        td = _dispatch()
        await recv.handle(td)

        result = recv.get_result(td.task_id)
        assert isinstance(result, TaskComplete)
        assert result.results == [{"val": 42}]

    @pytest.mark.asyncio
    async def test_no_execute_fn_drops_silently(self):
        """If no execute_fn set, task is dropped without error."""
        recv = TaskReceiver()
        await recv.handle(_dispatch())
        assert recv.completed_count == 0
        assert recv.active_count == 0

    @pytest.mark.asyncio
    async def test_sequential_tasks_fifo(self):
        """Multiple independent tasks execute in order."""
        order: list[str] = []

        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            order.append(td.task_id)
            return _complete(task_id=td.task_id)

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)

        td1 = _dispatch(task_id="task-first")
        td2 = _dispatch(task_id="task-second")
        await recv.handle(td1)
        await recv.handle(td2)

        assert order == ["task-first", "task-second"]
        assert recv.completed_count == 2


# =========================================================================
# Epic 10.8 -- TaskReceiver error handling
# =========================================================================


class TestTaskReceiverErrors:
    """10.8.3 -- TaskReceiver error handling when execute_fn raises."""

    @pytest.mark.asyncio
    async def test_exception_produces_task_failed(self):
        async def failing_execute(td: TaskDispatch) -> TaskComplete:
            raise RuntimeError("capability unavailable")

        recv = TaskReceiver()
        recv.set_execute_fn(failing_execute)
        td = _dispatch(task_id="task-fail")
        await recv.handle(td)

        assert recv.failed_count == 1
        assert recv.completed_count == 0
        assert recv.active_count == 0

        result = recv.get_result("task-fail")
        assert isinstance(result, TaskFailed)
        assert result.reason == "internal_error"
        assert "capability unavailable" in result.last_error_detail

    @pytest.mark.asyncio
    async def test_error_does_not_block_subsequent_tasks(self):
        call_count = 0

        async def sometimes_failing(td: TaskDispatch) -> TaskComplete:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first fails")
            return _complete(task_id=td.task_id)

        recv = TaskReceiver()
        recv.set_execute_fn(sometimes_failing)

        await recv.handle(_dispatch(task_id="task-fail"))
        await recv.handle(_dispatch(task_id="task-ok"))

        assert recv.failed_count == 1
        assert recv.completed_count == 1


# =========================================================================
# Epic 10.8 -- TaskReceiver chained execution
# =========================================================================


class TestTaskReceiverChained:
    """10.8.4 -- TaskReceiver with chained tasks and dependency routing."""

    @pytest.mark.asyncio
    async def test_chained_task_buffered_then_released(self):
        """B waits for A, then hydrates and executes after A completes."""
        executed: list[str] = []

        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            executed.append(td.task_id)
            if td.task_id == "task-A":
                return _complete(
                    task_id="task-A",
                    results=[{"address": "123 Main St"}],
                )
            return _complete(
                task_id=td.task_id,
                results=[{"found": td.intents[0].params.get("near", "unknown")}],
            )

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)

        # Dispatch B first (depends on A) -- gets buffered
        td_b = _dispatch(
            task_id="task-B",
            intents=[_intent(params={"near": "$prev.result.address"})],
            depends_on="task-A",
        )
        await recv.handle(td_b)
        assert executed == []
        assert recv.waiting_count == 1

        # Dispatch A -- executes, then releases B
        td_a = _dispatch(task_id="task-A")
        await recv.handle(td_a)

        assert executed == ["task-A", "task-B"]
        assert recv.completed_count == 2
        assert recv.waiting_count == 0
        # B's params were hydrated
        assert td_b.intents[0].params["near"] == "123 Main St"

    @pytest.mark.asyncio
    async def test_three_deep_chain_via_receiver(self):
        """A -> B -> C: receiver manages full chain."""
        executed: list[str] = []

        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            executed.append(td.task_id)
            return _complete(
                task_id=td.task_id,
                results=[{"val": f"result-{td.task_id}"}],
            )

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)

        # Enqueue C (waits on B), then B (waits on A)
        td_c = _dispatch(
            task_id="task-C",
            intents=[_intent(params={"from_b": "$prev.result.val"})],
            depends_on="task-B",
        )
        td_b = _dispatch(
            task_id="task-B",
            intents=[_intent(params={"from_a": "$prev.result.val"})],
            depends_on="task-A",
        )
        await recv.handle(td_c)
        await recv.handle(td_b)
        assert executed == []
        assert recv.waiting_count == 2

        # Dispatch A -- cascades: A -> B -> C
        td_a = _dispatch(task_id="task-A")
        await recv.handle(td_a)

        assert executed == ["task-A", "task-B", "task-C"]
        assert recv.completed_count == 3
        assert recv.waiting_count == 0

    @pytest.mark.asyncio
    async def test_parent_failure_still_releases_children(self):
        """If parent fails, child is still released (with failure context)."""
        executed: list[str] = []

        async def failing_then_ok(td: TaskDispatch) -> TaskComplete:
            executed.append(td.task_id)
            if td.task_id == "task-A":
                raise RuntimeError("boom")
            return _complete(task_id=td.task_id)

        recv = TaskReceiver()
        recv.set_execute_fn(failing_then_ok)

        td_b = _dispatch(
            task_id="task-B",
            intents=[_intent(params={"x": "$prev.result._parent_failed"})],
            depends_on="task-A",
        )
        await recv.handle(td_b)

        td_a = _dispatch(task_id="task-A")
        await recv.handle(td_a)

        # A failed, but B was still released (with synthetic result)
        assert "task-A" in executed
        assert "task-B" in executed
        assert recv.failed_count == 1  # A failed
        # B executed with the synthetic parent failure result


# =========================================================================
# Epic 10.8 -- TaskReceiver clear and get_result
# =========================================================================


class TestTaskReceiverClearAndResults:
    """10.8.5 -- TaskReceiver clear() and get_result()."""

    @pytest.mark.asyncio
    async def test_clear_resets_all(self):
        async def fake_execute(td: TaskDispatch) -> TaskComplete:
            return _complete(task_id=td.task_id)

        recv = TaskReceiver()
        recv.set_execute_fn(fake_execute)
        await recv.handle(_dispatch(task_id="task-1"))
        assert recv.completed_count == 1

        recv.clear()
        assert recv.completed_count == 0
        assert recv.failed_count == 0
        assert recv.active_count == 0
        assert recv.get_result("task-1") is None

    def test_get_result_returns_none_for_unknown(self):
        recv = TaskReceiver()
        assert recv.get_result("task-nonexistent") is None


# =========================================================================
# Epic 10.9 -- IntentResult
# =========================================================================


class TestIntentResult:
    """10.9.1 -- IntentResult dataclass."""

    def test_default_success(self):
        r = IntentResult(intent_index=0, action="test")
        assert r.status == "success"
        assert r.data == {}
        assert r.error is None
        assert r.tool_calls_used == 0

    def test_with_data(self):
        r = IntentResult(
            intent_index=0,
            action="search",
            data={"results": [1, 2, 3]},
            tool_calls_used=2,
        )
        assert r.data == {"results": [1, 2, 3]}
        assert r.tool_calls_used == 2

    def test_error_status(self):
        r = IntentResult(
            intent_index=1,
            action="book",
            status="error",
            error="timeout",
        )
        assert r.status == "error"
        assert r.error == "timeout"

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="success.*error"):
            IntentResult(intent_index=0, action="test", status="unknown")

    def test_to_dict_success(self):
        r = IntentResult(
            intent_index=0,
            action="search",
            data={"count": 5},
        )
        d = r.to_dict()
        assert d["action"] == "search"
        assert d["status"] == "success"
        assert d["data"] == {"count": 5}
        assert "error" not in d

    def test_to_dict_error(self):
        r = IntentResult(
            intent_index=0,
            action="book",
            status="error",
            error="timeout",
        )
        d = r.to_dict()
        assert d["error"] == "timeout"
        assert d["status"] == "error"


# =========================================================================
# Epic 10.9 -- BundledExecutionPlan: single intent
# =========================================================================


class TestBundledPlanSingle:
    """10.9.2 -- BundledExecutionPlan with single intent."""

    def test_single_intent_plan(self):
        plan = BundledExecutionPlan(intents=[_intent(action="weather")])
        assert plan.current_intent is not None
        assert plan.current_intent.action == "weather"
        assert plan.is_complete is False
        assert plan.total_intents == 1
        assert plan.completed_intents == 0

    def test_record_and_complete(self):
        plan = BundledExecutionPlan(intents=[_intent(action="weather")])
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="weather",
                data={"temp": 72},
                tool_calls_used=1,
            )
        )
        assert plan.is_complete is True
        assert plan.current_intent is None
        assert plan.total_tool_calls == 1
        assert plan.completed_intents == 1

    def test_combined_result(self):
        plan = BundledExecutionPlan(intents=[_intent(action="weather")])
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="weather",
                data={"temp": 72},
                tool_calls_used=1,
            )
        )
        combined = plan.combined_result()
        assert combined["all_success"] is True
        assert combined["total_tool_calls"] == 1
        assert combined["completed_intents"] == 1
        assert combined["total_intents"] == 1
        assert len(combined["intent_results"]) == 1
        assert combined["intent_results"][0]["action"] == "weather"


# =========================================================================
# Epic 10.9 -- BundledExecutionPlan: multiple intents
# =========================================================================


class TestBundledPlanMultiple:
    """10.9.3 -- BundledExecutionPlan with bundled intents."""

    def test_two_intents_sequential(self):
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="book hotel"),
                _intent(action="search restaurants"),
            ]
        )
        assert plan.current_intent.action == "book hotel"
        assert plan.current_index == 0

        plan.record_result(
            IntentResult(
                intent_index=0,
                action="book hotel",
                data={"confirmation": "ACM-123"},
                tool_calls_used=1,
            )
        )
        assert plan.current_intent.action == "search restaurants"
        assert plan.current_index == 1
        assert plan.is_complete is False

        plan.record_result(
            IntentResult(
                intent_index=1,
                action="search restaurants",
                data={"restaurants": ["A", "B"]},
                tool_calls_used=2,
            )
        )
        assert plan.is_complete is True
        assert plan.total_tool_calls == 3

    def test_combined_result_all_success(self):
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="a1"),
                _intent(action="a2"),
            ]
        )
        plan.record_result(IntentResult(intent_index=0, action="a1", data={"x": 1}))
        plan.record_result(IntentResult(intent_index=1, action="a2", data={"y": 2}))
        combined = plan.combined_result()
        assert combined["all_success"] is True
        assert combined["total_intents"] == 2
        assert combined["completed_intents"] == 2
        assert len(combined["intent_results"]) == 2

    def test_three_intents(self):
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="a1"),
                _intent(action="a2"),
                _intent(action="a3"),
            ]
        )
        for i in range(3):
            plan.record_result(
                IntentResult(
                    intent_index=i,
                    action=f"a{i + 1}",
                    tool_calls_used=1,
                )
            )
        assert plan.is_complete is True
        assert plan.total_tool_calls == 3


# =========================================================================
# Epic 10.9 -- BundledExecutionPlan: error handling
# =========================================================================


class TestBundledPlanErrors:
    """10.9.4 -- BundledExecutionPlan error scenarios."""

    def test_wrong_index_raises(self):
        plan = BundledExecutionPlan(intents=[_intent(action="a")])
        with pytest.raises(ValueError, match="Expected result for intent 0"):
            plan.record_result(IntentResult(intent_index=1, action="a"))

    def test_record_after_complete_raises(self):
        plan = BundledExecutionPlan(intents=[_intent(action="a")])
        plan.record_result(IntentResult(intent_index=0, action="a"))
        with pytest.raises(RuntimeError, match="complete"):
            plan.record_result(IntentResult(intent_index=1, action="b"))

    def test_partial_failure(self):
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="a"),
                _intent(action="b"),
            ]
        )
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="a",
                data={"ok": True},
            )
        )
        plan.record_result(
            IntentResult(
                intent_index=1,
                action="b",
                status="error",
                error="timeout",
            )
        )
        combined = plan.combined_result()
        assert combined["all_success"] is False
        assert combined["intent_results"][1]["error"] == "timeout"

    def test_all_success_false_with_error(self):
        plan = BundledExecutionPlan(intents=[_intent(action="a")])
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="a",
                status="error",
                error="fail",
            )
        )
        assert plan.all_success is False
        assert plan.has_errors is True


# =========================================================================
# Epic 10.9 -- BundledExecutionPlan: properties
# =========================================================================


class TestBundledPlanProperties:
    """10.9.5 -- BundledExecutionPlan property accessors."""

    def test_total_intents(self):
        plan = BundledExecutionPlan(intents=[_intent(), _intent(action="b")])
        assert plan.total_intents == 2

    def test_completed_intents_increments(self):
        plan = BundledExecutionPlan(intents=[_intent(), _intent(action="b")])
        assert plan.completed_intents == 0
        plan.record_result(IntentResult(intent_index=0, action="a"))
        assert plan.completed_intents == 1

    def test_all_success_empty(self):
        """Empty results list: all_success is True (vacuously)."""
        plan = BundledExecutionPlan(intents=[_intent()])
        assert plan.all_success is True

    def test_has_errors_false_initially(self):
        plan = BundledExecutionPlan(intents=[_intent()])
        assert plan.has_errors is False

    def test_results_as_list(self):
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="a1"),
                _intent(action="a2"),
            ]
        )
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="a1",
                data={"x": 1},
            )
        )
        plan.record_result(
            IntentResult(
                intent_index=1,
                action="a2",
                data={"y": 2},
            )
        )
        results = plan.results_as_list()
        assert results == [{"x": 1}, {"y": 2}]

    def test_results_as_list_filters_errors(self):
        """results_as_list only includes successful intent data."""
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="a1"),
                _intent(action="a2"),
            ]
        )
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="a1",
                data={"ok": True},
            )
        )
        plan.record_result(
            IntentResult(
                intent_index=1,
                action="a2",
                status="error",
                error="fail",
            )
        )
        results = plan.results_as_list()
        assert len(results) == 1
        assert results[0] == {"ok": True}

    def test_combined_result_before_complete(self):
        """combined_result works even when plan isn't complete."""
        plan = BundledExecutionPlan(
            intents=[
                _intent(action="a1"),
                _intent(action="a2"),
            ]
        )
        plan.record_result(
            IntentResult(
                intent_index=0,
                action="a1",
                data={"x": 1},
            )
        )
        combined = plan.combined_result()
        assert combined["completed_intents"] == 1
        assert combined["total_intents"] == 2


# =========================================================================
# Package structure tests
# =========================================================================


class TestPackageStructure:
    """10.x -- Package-level exports for epics 10.1-10.9."""

    def test_all_exports_count(self):
        """Package exports exactly 33 symbols (29 + 4 parallel_safety)."""
        import poc.k1_poc.task as pkg

        assert len(pkg.__all__) == 33

    def test_new_modules_importable(self):
        """Epics 10.7-10.9 modules import without error."""
        from poc.k1_poc.task import bundled_executor, receiver, tools

        assert hasattr(tools, "dispatch_task")
        assert hasattr(tools, "DISPATCH_TASK_SCHEMA")
        assert hasattr(receiver, "TaskReceiver")
        assert hasattr(bundled_executor, "BundledExecutionPlan")
        assert hasattr(bundled_executor, "IntentResult")

    def test_all_exports_accessible(self):
        """Every name in __all__ is accessible on the package."""
        import poc.k1_poc.task as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{name} in __all__ but not accessible"
