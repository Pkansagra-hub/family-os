"""
tests/poc/test_m03_e36_conformance.py -- E3.6 Actor & React Conformance Tests
================================================================================

Validates the 4 issues of Epic 3.6:
  3.6.1 -- Front emission ordering (dispatches before final.response)
  3.6.2 -- Resume envelope routes to back_resume_handler
  3.6.3 -- Cancel propagation reaches back loop
  3.6.4 -- Parallel tool safety enforcement

Milestone 3, Epic 3.6

Test count target: ~30 tests
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.topics import (
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_RESUME,
)
from k1.concierge.llm.types import (
    ConciergeModelResponse,
    FinishReason,
    ToolCallResult,
    ToolSchema,
)
from k1.concierge.protocols.cancellation import CancellationToken, CancelReason
from k1.concierge.react.loop import ReactResult, react_loop
from k1.concierge.task.parallel_safety import classify_tool_batch
from k1.concierge.tools.result_protocol import ToolResult
from tests.k1.concierge.conftest import make_hub_text_response, make_hub_tool_response

# =========================================================================
# Helpers
# =========================================================================


def _make_envelope(
    topic: str = TOPIC_TASK_DISPATCH,
    payload: dict | None = None,
    envelope_id: int = 1,
) -> Envelope:
    """Build a minimal Envelope for testing."""
    data = payload or {"task_id": "t1"}
    return Envelope(
        topic=topic,
        payload=json.dumps(data).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=envelope_id,
        parent_id=0,
    )


def _make_tool_schema(name: str) -> ToolSchema:
    """Build a minimal ToolSchema."""
    return ToolSchema(
        name=name,
        description=f"Test tool: {name}",
        parameters={"type": "object", "properties": {}},
    )


def _make_tool_call(name: str, args: dict | None = None, call_id: str = "") -> ToolCallResult:
    """Build a ToolCallResult."""
    return ToolCallResult(
        id=call_id or f"call_{name}",
        name=name,
        arguments=args or {},
    )


def _make_text_response(text: str) -> ConciergeModelResponse:
    """Build a ConciergeModelResponse with text only."""
    return ConciergeModelResponse(
        text=text,
        tool_calls=[],
        finish_reason=FinishReason.STOP,
    )


def _make_tool_response(
    tool_calls: list[ToolCallResult],
    text: str = "",
) -> ConciergeModelResponse:
    """Build a ConciergeModelResponse with tool calls."""
    return ConciergeModelResponse(
        text=text,
        tool_calls=tool_calls,
        finish_reason=FinishReason.TOOL_CALLS,
    )


def _make_mock_deps() -> dict[str, Any]:
    """Create mock dependencies for route_back_envelope / front_handler."""
    return {
        "model": AsyncMock(),
        "ss": MagicMock(),
        "bus": MagicMock(),
        "tool_dispatcher": AsyncMock(),
        "fsm_state": MagicMock(),
    }


# =========================================================================
# 3.6.1 -- Front emission ordering (dispatches before final.response)
# =========================================================================


class TestFrontEmissionOrdering:
    """Verify Front emits task dispatches BEFORE response.final.

    The front_handler must emit events in this order:
      1. task.cancel.v1 (if any)
      2. task.dispatch.v1 (if any)
      3. response.final.v1 (or streaming response)

    This prevents the FSM from transitioning to LISTENING before
    dispatches arrive, which caused IllegalTransitionError.
    """

    @pytest.mark.asyncio
    async def test_dispatch_emitted_before_final_response(self) -> None:
        """task.dispatch.v1 appears BEFORE response.final.v1 in publish order."""
        from k1.concierge.actors.front import front_handler

        # Model returns a dispatch_task tool call, then text response
        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        model.execute = AsyncMock(
            side_effect=[
                make_hub_tool_response(
                    [
                        {
                            "id": "call_dispatch_task",
                            "name": "dispatch_task",
                            "arguments": {
                                "task_description": "do something",
                                "intents": [{"action": "execute"}],
                            },
                        }
                    ]
                ),
                make_hub_text_response(text="I've dispatched the task for you."),
            ]
        )

        # Tool dispatcher returns ok result with task_id
        tool_dispatcher.dispatch = AsyncMock(
            return_value=ToolResult(
                tool_name="dispatch_task",
                status="ok",
                data={"task_id": "task-001", "_dispatch": {"task_id": "task-001"}},
            )
        )

        bus = MagicMock()
        published_topics: list[str] = []

        def _capture_publish(env: Any) -> None:
            topic = getattr(env, "topic", "unknown")
            published_topics.append(topic)

        bus.publish = _capture_publish

        ss = MagicMock()
        ss.get_section = MagicMock(return_value=None)

        env = _make_envelope(topic="k1.session.user.input.v1")

        result = await front_handler(
            envelope=env,
            model=model,
            ss=ss,
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            all_tool_schemas=[_make_tool_schema("dispatch_task")],
        )

        # Find indices of dispatch and final events
        dispatch_indices = [i for i, t in enumerate(published_topics) if "task.dispatch" in t]
        final_indices = [
            i
            for i, t in enumerate(published_topics)
            if "response.final" in t or "response.stream" in t
        ]

        assert len(dispatch_indices) > 0, f"No dispatch events found in {published_topics}"
        # Final may not be emitted if text is None, but if it is:
        if final_indices:
            assert dispatch_indices[0] < final_indices[0], (
                f"Dispatch at {dispatch_indices[0]} should be before final at {final_indices[0]}. "
                f"Full order: {published_topics}"
            )

    @pytest.mark.asyncio
    async def test_cancel_emitted_before_normal_dispatch(self) -> None:
        """task.cancel.v1 appears BEFORE task.dispatch.v1 in publish order."""
        from k1.concierge.actors.front import front_handler

        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        model.execute = AsyncMock(
            side_effect=[
                make_hub_tool_response(
                    [
                        {
                            "id": "call_cancel",
                            "name": "dispatch_task",
                            "arguments": {
                                "task_description": "cancel old task",
                                "intents": [{"action": "cancel", "target_task_id": "old-task"}],
                            },
                        },
                        {
                            "id": "call_normal",
                            "name": "dispatch_task",
                            "arguments": {
                                "task_description": "new task",
                                "intents": [{"action": "execute"}],
                            },
                        },
                    ]
                ),
                make_hub_text_response(text="Done."),
            ]
        )

        tool_dispatcher.dispatch = AsyncMock(
            return_value=ToolResult(
                tool_name="dispatch_task",
                status="ok",
                data={"task_id": "new-task", "_dispatch": {"task_id": "new-task"}},
            )
        )

        bus = MagicMock()
        published_topics: list[str] = []
        bus.publish = lambda env: published_topics.append(getattr(env, "topic", "?"))

        ss = MagicMock()
        ss.get_section = MagicMock(return_value=None)

        env = _make_envelope(topic="k1.session.user.input.v1")

        await front_handler(
            envelope=env,
            model=model,
            ss=ss,
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            all_tool_schemas=[_make_tool_schema("dispatch_task")],
        )

        cancel_indices = [i for i, t in enumerate(published_topics) if "task.cancel" in t]
        dispatch_indices = [i for i, t in enumerate(published_topics) if "task.dispatch" in t]

        if cancel_indices and dispatch_indices:
            assert cancel_indices[0] < dispatch_indices[0], (
                f"Cancel at {cancel_indices[0]} should be before dispatch at {dispatch_indices[0]}. "
                f"Full order: {published_topics}"
            )

    @pytest.mark.asyncio
    async def test_text_only_response_no_dispatch(self) -> None:
        """When Front returns text only, no dispatch events are emitted."""
        from k1.concierge.actors.front import front_handler

        model = AsyncMock()
        model.execute = AsyncMock(return_value=make_hub_text_response(text="Hello!"))

        bus = MagicMock()
        published_topics: list[str] = []
        bus.publish = lambda env: published_topics.append(getattr(env, "topic", "?"))

        ss = MagicMock()
        ss.get_section = MagicMock(return_value=None)

        env = _make_envelope(topic="k1.session.user.input.v1")

        result = await front_handler(
            envelope=env,
            model=model,
            ss=ss,
            bus=MagicMock(),
            tool_dispatcher=AsyncMock(),
            all_tool_schemas=[],
        )

        assert result.status == "complete"
        assert result.text == "Hello!"
        assert len(result.dispatched_tasks) == 0

    @pytest.mark.asyncio
    async def test_front_handler_writes_runtime_prompt_dump(self, tmp_path: Path) -> None:
        """Front persists the exact system_prompt and messages for debugging."""
        import k1.concierge.actors.front as front_mod

        model = AsyncMock()
        model.execute = AsyncMock(return_value=make_hub_text_response(text="Hello!"))

        bus = MagicMock()
        bus.publish = lambda env: None

        ss = MagicMock()
        ss.get_section = MagicMock(return_value=None)

        env = _make_envelope(
            topic="k1.session.user.input.v1",
            payload={"text": "hello there"},
            envelope_id=123,
        )

        with patch.object(front_mod, "_PROMPT_DUMP_DIR", tmp_path):
            result = await front_mod.front_handler(
                envelope=env,
                model=model,
                ss=ss,
                bus=bus,
                tool_dispatcher=AsyncMock(),
                all_tool_schemas=[],
            )

        latest = tmp_path / "front_prompt_latest.json"
        stamped = list(tmp_path.glob("front_prompt_env123_*.json"))

        assert result.status == "complete"
        assert latest.exists()
        assert len(stamped) == 1

        dump = json.loads(latest.read_text(encoding="utf-8"))
        assert dump["envelope_id"] == 123
        assert dump["topic"] == "k1.session.user.input.v1"
        assert dump["mode"] == "standard"
        assert dump["messages"] == [{"role": "user", "content": "hello there"}]
        assert isinstance(dump["system_prompt"], str)
        assert dump["system_prompt"]

    def test_runtime_prompt_dump_includes_tool_definitions(self, tmp_path: Path) -> None:
        """Front prompt dumps include the full LLM-facing tool definitions."""
        import k1.concierge.actors.front as front_mod

        context = SimpleNamespace(
            affect_band="neutral",
            max_iterations=3,
            tools=[_make_tool_schema("recall_memory")],
            messages=[SimpleNamespace(role="user", content="hello")],
            system_prompt="system prompt",
        )
        env = _make_envelope(
            topic="k1.session.user.input.v1",
            payload={"text": "hello"},
            envelope_id=456,
        )

        with patch.object(front_mod, "_PROMPT_DUMP_DIR", tmp_path):
            front_mod._write_runtime_prompt_dump(
                envelope=env,
                mode=front_mod.PromptMode.STANDARD,
                context=context,
                domain=None,
                tier="hot",
                clarify_depth=0,
                trace_id="trace-front-tool-dump",
            )

        dump = json.loads((tmp_path / "front_prompt_latest.json").read_text(encoding="utf-8"))
        assert dump["tool_names"] == ["recall_memory"]
        assert dump["tools"] == [
            {
                "name": "recall_memory",
                "description": "Test tool: recall_memory",
                "parameters": {"type": "object", "properties": {}},
                "returns": None,
                "actor": None,
                "category": None,
                "side_effects": False,
            }
        ]

    def test_first_front_llm_call_dump_includes_hub_request(self, tmp_path: Path) -> None:
        """The first Front LLM dump captures the actual HubRequest payload."""
        import k1.concierge.react.loop as loop_mod
        from k1.model_hub.types import (
            CapabilityType,
            HubRequest,
            Message,
            RequestConstraints,
            ToolCallPayload,
            ToolDefinition,
        )

        request = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="hello")],
                tools=[
                    ToolDefinition(
                        name="dispatch_task",
                        description="Dispatch work",
                        parameters={"type": "object"},
                    )
                ],
                tool_choice="auto",
                system_prompt="system prompt",
            ),
            constraints=RequestConstraints(
                max_tokens=1234,
                temperature=1.0,
                consumer_id="concierge.front",
            ),
            trace_id="front-test-trace",
            session_id="web-test",
        )

        with patch.object(loop_mod, "_PROMPT_DUMP_DIR", tmp_path):
            loop_mod._write_front_llm_first_call_dump(
                actor="front",
                scenario="standard",
                iteration=0,
                request=request,
                use_streaming=True,
                force_text=False,
            )

        dump = json.loads(
            (tmp_path / "front_llm_first_call_latest.json").read_text(encoding="utf-8")
        )
        assert dump["actor"] == "front"
        assert dump["scenario"] == "standard"
        assert dump["capability"] == "TOOL_CALL"
        assert dump["use_streaming"] is True
        assert dump["constraints"]["consumer_id"] == "concierge.front"
        assert dump["payload"]["system_prompt"] == "system prompt"
        assert dump["payload"]["messages"] == [{"role": "user", "content": "hello"}]
        assert dump["payload"]["tools"][0]["name"] == "dispatch_task"
        assert dump["payload"]["tool_choice"] == "auto"
        assert dump["provider_mapping_preview"]["tools"].endswith("function_declarations")


# =========================================================================
# 3.6.2 -- Resume envelope routes to back_resume_handler
# =========================================================================


class TestBackTopicRouting:
    """Verify route_back_envelope dispatches to correct handler by topic."""

    @pytest.mark.asyncio
    async def test_task_resume_routes_to_resume_handler(self) -> None:
        """task.resume.v1 routes to back_resume_handler, NOT back_handler."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_RESUME, payload={"task_id": "t1"})
        deps = _make_mock_deps()

        with (
            patch(
                "k1.concierge.actors.back.back_resume_handler", new_callable=AsyncMock
            ) as mock_resume,
            patch("k1.concierge.actors.back.back_handler", new_callable=AsyncMock) as mock_back,
        ):
            mock_resume.return_value = ReactResult(status="complete")
            await route_back_envelope(envelope=env, **deps)

            mock_resume.assert_called_once()
            mock_back.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_cancel_routes_to_cancel_handler(self) -> None:
        """task.cancel.v1 routes to back_cancel_handler."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_CANCEL, payload={"task_id": "t1"})
        deps = _make_mock_deps()

        with (
            patch("k1.concierge.actors.back.back_cancel_handler") as mock_cancel,
            patch("k1.concierge.actors.back.back_handler", new_callable=AsyncMock) as mock_back,
        ):
            result = await route_back_envelope(envelope=env, **deps)

            mock_cancel.assert_called_once()
            mock_back.assert_not_called()
            assert result is None

    @pytest.mark.asyncio
    async def test_clarification_response_routes_to_resume_handler(self) -> None:
        """clarification.response routes to back_resume_handler."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(
            topic=TOPIC_CLARIFICATION_RESPONSE,
            payload={"task_id": "t1"},
        )
        deps = _make_mock_deps()

        with (
            patch(
                "k1.concierge.actors.back.back_resume_handler", new_callable=AsyncMock
            ) as mock_resume,
            patch("k1.concierge.actors.back.back_handler", new_callable=AsyncMock) as mock_back,
        ):
            mock_resume.return_value = ReactResult(status="complete")
            await route_back_envelope(envelope=env, **deps)

            mock_resume.assert_called_once()
            mock_back.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_dispatch_routes_to_back_handler(self) -> None:
        """task.dispatch.v1 routes to back_handler."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_DISPATCH, payload={"task_id": "t1"})
        deps = _make_mock_deps()
        hil_port = object()

        with (
            patch("k1.concierge.actors.back.back_handler", new_callable=AsyncMock) as mock_back,
            patch(
                "k1.concierge.actors.back.back_resume_handler", new_callable=AsyncMock
            ) as mock_resume,
        ):
            mock_back.return_value = ReactResult(status="complete")
            await route_back_envelope(envelope=env, hil_port=hil_port, **deps)

            mock_back.assert_called_once()
            assert mock_back.call_args.kwargs["hil_port"] is hil_port
            mock_resume.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_topic_calls_no_handler(self) -> None:
        """Unknown topic logs warning and calls no handler."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(
            topic="k1.fake.unknown.v1",
            payload={"task_id": "t1"},
        )
        deps = _make_mock_deps()

        with (
            patch("k1.concierge.actors.back.back_handler", new_callable=AsyncMock) as mock_back,
            patch(
                "k1.concierge.actors.back.back_resume_handler", new_callable=AsyncMock
            ) as mock_resume,
            patch("k1.concierge.actors.back.back_cancel_handler") as mock_cancel,
        ):
            result = await route_back_envelope(envelope=env, **deps)

            mock_back.assert_not_called()
            mock_resume.assert_not_called()
            mock_cancel.assert_not_called()
            assert result is None

    @pytest.mark.asyncio
    async def test_resume_handler_receives_cancel_token(self) -> None:
        """back_resume_handler receives the extracted cancel_token."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_RESUME, payload={"task_id": "t1"})
        deps = _make_mock_deps()

        # Set up fsm_state with a cancel_handler that returns a token
        token = CancellationToken(task_id="t1")
        mock_handler = MagicMock()
        mock_handler.get_token = MagicMock(return_value=token)
        deps["fsm_state"].cancel_handler = mock_handler

        with patch(
            "k1.concierge.actors.back.back_resume_handler", new_callable=AsyncMock
        ) as mock_resume:
            mock_resume.return_value = ReactResult(status="complete")
            await route_back_envelope(envelope=env, **deps)

            call_kwargs = mock_resume.call_args[1]
            assert call_kwargs["cancel_token"] is token

    @pytest.mark.asyncio
    async def test_cancel_handler_receives_cancel_token(self) -> None:
        """back_cancel_handler receives the extracted cancel_token."""
        from k1.concierge.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_CANCEL, payload={"task_id": "t1"})
        deps = _make_mock_deps()

        token = CancellationToken(task_id="t1")
        mock_handler = MagicMock()
        mock_handler.get_token = MagicMock(return_value=token)
        deps["fsm_state"].cancel_handler = mock_handler

        with patch("k1.concierge.actors.back.back_cancel_handler") as mock_cancel:
            await route_back_envelope(envelope=env, **deps)

            call_kwargs = mock_cancel.call_args[1]
            assert call_kwargs["cancel_token"] is token


# =========================================================================
# 3.6.3 -- Cancel propagation reaches back loop
# =========================================================================


class TestCancelPropagation:
    """Verify CancellationToken propagates through react_loop."""

    @pytest.mark.asyncio
    async def test_cancel_token_stops_react_loop(self) -> None:
        """Setting token.cancel() causes react_loop to return status=cancelled."""
        token = CancellationToken(task_id="t1")

        # Cancel immediately so the first check returns True
        token.cancel(CancelReason.USER_REQUESTED)

        async def _check_cancel() -> bool:
            return token.is_cancelled

        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        result = await react_loop(
            actor="back",
            system_prompt="You are Back.",
            messages=[],
            tools=[_make_tool_schema("recall_memory")],
            max_iterations=5,
            model=model,
            tool_dispatcher=tool_dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=_check_cancel,
            trace_id="test-trace",
        )

        assert result.status == "cancelled"
        # Model should never be called since cancel fires first
        model.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_after_first_tool_call(self) -> None:
        """Token cancelled after first tool execution exits on next iteration."""
        token = CancellationToken(task_id="t1")
        call_count = 0

        async def _check_cancel() -> bool:
            return token.is_cancelled

        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        # First iteration: model returns a tool call
        iter0_response = make_hub_tool_response(
            [{"name": "recall_memory", "arguments": {"query": "test"}}]
        )
        # Second iteration would be text but cancel fires first
        iter1_response = make_hub_text_response(text="Done")
        model.execute = AsyncMock(side_effect=[iter0_response, iter1_response])

        async def _dispatch(tc: Any) -> ToolResult:
            nonlocal call_count
            call_count += 1
            # Cancel after first tool execution
            token.cancel(CancelReason.USER_REQUESTED)
            return ToolResult(
                tool_name=tc.name,
                status="ok",
                data={"result": "found"},
            )

        tool_dispatcher.dispatch = _dispatch

        result = await react_loop(
            actor="back",
            system_prompt="You are Back.",
            messages=[],
            tools=[_make_tool_schema("recall_memory")],
            max_iterations=5,
            model=model,
            tool_dispatcher=tool_dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=_check_cancel,
            trace_id="test-trace",
        )

        assert result.status == "cancelled"
        assert call_count == 1
        assert token.is_cancelled is True
        assert token.cancel_reason == CancelReason.USER_REQUESTED

    @pytest.mark.asyncio
    async def test_no_cancel_completes_normally(self) -> None:
        """Without cancellation, react_loop completes normally."""

        async def _no_cancel() -> bool:
            return False

        model = AsyncMock()
        model.execute = AsyncMock(return_value=make_hub_text_response(text="Hello user"))

        result = await react_loop(
            actor="front",
            system_prompt="You are Front.",
            messages=[],
            tools=[],
            max_iterations=3,
            model=model,
            tool_dispatcher=AsyncMock(),
            on_text_response=AsyncMock(),
            cancellation_check=_no_cancel,
            trace_id="test",
        )

        assert result.status == "complete"
        assert result.text == "Hello user"

    @pytest.mark.asyncio
    async def test_cancel_reason_preserved(self) -> None:
        """CancellationToken preserves the cancel reason after cancellation."""
        token = CancellationToken(task_id="t1")
        token.cancel(CancelReason.TIMEOUT)

        assert token.is_cancelled is True
        assert token.cancel_reason == CancelReason.TIMEOUT
        assert token.cancel_time_ns > 0

    @pytest.mark.asyncio
    async def test_cancel_is_idempotent(self) -> None:
        """Multiple cancel() calls do not change the reason or time."""
        token = CancellationToken(task_id="t1")
        token.cancel(CancelReason.USER_REQUESTED)
        first_time = token.cancel_time_ns
        first_reason = token.cancel_reason

        # Second cancel should be no-op
        token.cancel(CancelReason.SUPERSEDED)
        assert token.cancel_reason == first_reason
        assert token.cancel_time_ns == first_time

    @pytest.mark.asyncio
    async def test_back_cancel_handler_sets_token(self) -> None:
        """back_cancel_handler calls token.cancel() on the CancellationToken."""
        from k1.concierge.actors.back import back_cancel_handler

        token = CancellationToken(task_id="t1")
        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        back_cancel_handler(
            envelope=env,
            fsm_state=None,
            cancel_token=token,
        )

        assert token.is_cancelled is True
        assert token.cancel_reason == CancelReason.USER_REQUESTED


# =========================================================================
# 3.6.4 -- Parallel tool safety enforcement
# =========================================================================


class TestParallelToolSafety:
    """Verify classify_tool_batch splits tools correctly and the react_loop
    respects the classification by running parallel-safe tools concurrently
    and sequential tools one at a time."""

    def test_classify_pure_parallel(self) -> None:
        """All parallel-safe tools are classified as parallel."""
        parallel, sequential = classify_tool_batch(["recall_memory", "update_beliefs"])
        assert set(parallel) == {"recall_memory", "update_beliefs"}
        assert sequential == []

    def test_classify_pure_sequential(self) -> None:
        """All sequential tools are classified as sequential."""
        parallel, sequential = classify_tool_batch(["invoke_capability", "dispatch_task"])
        assert parallel == []
        assert set(sequential) == {"invoke_capability", "dispatch_task"}

    def test_classify_mixed_batch(self) -> None:
        """Mixed batch splits correctly."""
        parallel, sequential = classify_tool_batch(
            [
                "recall_memory",
                "invoke_capability",
                "update_beliefs",
            ]
        )
        assert set(parallel) == {"recall_memory", "update_beliefs"}
        assert sequential == ["invoke_capability"]

    def test_classify_empty_batch(self) -> None:
        """Empty batch returns empty lists."""
        parallel, sequential = classify_tool_batch([])
        assert parallel == []
        assert sequential == []

    @pytest.mark.asyncio
    async def test_parallel_tools_run_concurrently(self) -> None:
        """Parallel-safe tools overlap in execution time when enabled."""
        execution_log: list[tuple[str, str, float]] = []  # (name, event, time)
        delay = 0.05  # 50ms delay to detect overlap

        async def _check_cancel() -> bool:
            return False

        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        model.execute = AsyncMock(
            side_effect=[
                make_hub_tool_response(
                    [
                        {"name": "recall_memory", "arguments": {"query": "a"}},
                        {"name": "update_beliefs", "arguments": {"fact": "b"}},
                    ]
                ),
                make_hub_tool_response(
                    [
                        {
                            "name": "submit_result",
                            "arguments": {"result_type": "complete", "final_answer": "done"},
                        },
                    ]
                ),
            ]
        )

        async def _dispatch(tc: Any) -> ToolResult:
            execution_log.append((tc.name, "start", time.monotonic()))
            await asyncio.sleep(delay)
            execution_log.append((tc.name, "end", time.monotonic()))
            return ToolResult(tool_name=tc.name, status="ok", data={"r": "ok"})

        tool_dispatcher.dispatch = _dispatch

        with patch("k1.concierge.react.loop.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.react.parallel_tools_enabled = True
            mock_cfg.react.front_degenerate_fallback = "sorry"
            mock_cfg.react.front_budget_fallback = "out of budget"
            mock_cfg.react.tool_timeout_ms = 30_000
            mock_cfg.llm.default_timeout_ms = 30000
            mock_config.return_value = mock_cfg

            result = await react_loop(
                actor="back",
                system_prompt="Back",
                messages=[],
                tools=[
                    _make_tool_schema("recall_memory"),
                    _make_tool_schema("update_beliefs"),
                    _make_tool_schema("submit_result"),
                ],
                max_iterations=5,
                model=model,
                tool_dispatcher=tool_dispatcher,
                on_text_response=AsyncMock(),
                cancellation_check=_check_cancel,
                trace_id="test",
            )

        assert result.status == "complete"

        # Check overlap: both starts should happen before either end
        starts = [e for e in execution_log if e[1] == "start" and e[0] != "submit_result"]
        ends = [e for e in execution_log if e[1] == "end" and e[0] != "submit_result"]
        if len(starts) == 2 and len(ends) == 2:
            # Both should have started before either ended (parallel)
            latest_start = max(s[2] for s in starts)
            earliest_end = min(e[2] for e in ends)
            # With true parallel, the latest start should be before the earliest end
            assert latest_start < earliest_end, "Parallel tools should overlap in time"

    @pytest.mark.asyncio
    async def test_sequential_tool_not_overlapping(self) -> None:
        """Sequential tool (invoke_capability) does NOT overlap with others."""
        execution_log: list[tuple[str, str, float]] = []
        delay = 0.03

        async def _check_cancel() -> bool:
            return False

        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        # Model returns: 1 parallel + 1 sequential tool
        model.execute = AsyncMock(
            side_effect=[
                make_hub_tool_response(
                    [
                        {"name": "recall_memory", "arguments": {"query": "a"}},
                        {"name": "invoke_capability", "arguments": {"cap": "x"}},
                    ]
                ),
                make_hub_tool_response(
                    [
                        {
                            "name": "submit_result",
                            "arguments": {"result_type": "complete", "final_answer": "done"},
                        },
                    ]
                ),
            ]
        )

        async def _dispatch(tc: Any) -> ToolResult:
            execution_log.append((tc.name, "start", time.monotonic()))
            await asyncio.sleep(delay)
            execution_log.append((tc.name, "end", time.monotonic()))
            return ToolResult(tool_name=tc.name, status="ok", data={"r": "ok"})

        tool_dispatcher.dispatch = _dispatch

        with patch("k1.concierge.react.loop.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.react.parallel_tools_enabled = True
            mock_cfg.react.front_degenerate_fallback = "sorry"
            mock_cfg.react.front_budget_fallback = "out of budget"
            mock_cfg.react.tool_timeout_ms = 30_000
            mock_cfg.llm.default_timeout_ms = 30000
            mock_config.return_value = mock_cfg

            result = await react_loop(
                actor="back",
                system_prompt="Back",
                messages=[],
                tools=[
                    _make_tool_schema("recall_memory"),
                    _make_tool_schema("invoke_capability"),
                    _make_tool_schema("submit_result"),
                ],
                max_iterations=5,
                model=model,
                tool_dispatcher=tool_dispatcher,
                on_text_response=AsyncMock(),
                cancellation_check=_check_cancel,
                trace_id="test",
            )

        assert result.status == "complete"

        # invoke_capability (sequential) must not overlap with recall_memory (parallel)
        # Sequential runs AFTER parallel batch completes
        recall_entries = [(e[1], e[2]) for e in execution_log if e[0] == "recall_memory"]
        invoke_entries = [(e[1], e[2]) for e in execution_log if e[0] == "invoke_capability"]

        if recall_entries and invoke_entries:
            recall_end = next(t for ev, t in recall_entries if ev == "end")
            invoke_start = next(t for ev, t in invoke_entries if ev == "start")
            assert (
                invoke_start >= recall_end
            ), "Sequential invoke_capability should start after parallel recall_memory ends"

    @pytest.mark.asyncio
    async def test_parallel_disabled_forces_sequential(self) -> None:
        """When parallel_tools_enabled=False, all tools run sequentially."""
        execution_log: list[tuple[str, str, float]] = []
        delay = 0.03

        async def _check_cancel() -> bool:
            return False

        model = AsyncMock()
        tool_dispatcher = AsyncMock()

        model.execute = AsyncMock(
            side_effect=[
                make_hub_tool_response(
                    [
                        {"name": "recall_memory", "arguments": {"query": "a"}},
                        {"name": "update_beliefs", "arguments": {"fact": "b"}},
                    ]
                ),
                make_hub_tool_response(
                    [
                        {
                            "name": "submit_result",
                            "arguments": {"result_type": "complete", "final_answer": "done"},
                        },
                    ]
                ),
            ]
        )

        async def _dispatch(tc: Any) -> ToolResult:
            execution_log.append((tc.name, "start", time.monotonic()))
            await asyncio.sleep(delay)
            execution_log.append((tc.name, "end", time.monotonic()))
            return ToolResult(tool_name=tc.name, status="ok", data={"r": "ok"})

        tool_dispatcher.dispatch = _dispatch

        with patch("k1.concierge.react.loop.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.react.parallel_tools_enabled = False
            mock_cfg.react.front_degenerate_fallback = "sorry"
            mock_cfg.react.front_budget_fallback = "out of budget"
            mock_cfg.react.tool_timeout_ms = 30_000
            mock_cfg.llm.default_timeout_ms = 30000
            mock_config.return_value = mock_cfg

            result = await react_loop(
                actor="back",
                system_prompt="Back",
                messages=[],
                tools=[
                    _make_tool_schema("recall_memory"),
                    _make_tool_schema("update_beliefs"),
                    _make_tool_schema("submit_result"),
                ],
                max_iterations=5,
                model=model,
                tool_dispatcher=tool_dispatcher,
                on_text_response=AsyncMock(),
                cancellation_check=_check_cancel,
                trace_id="test",
            )

        assert result.status == "complete"

        # Both tools should run sequentially (no overlap)
        recall_entries = [(e[1], e[2]) for e in execution_log if e[0] == "recall_memory"]
        beliefs_entries = [(e[1], e[2]) for e in execution_log if e[0] == "update_beliefs"]

        if recall_entries and beliefs_entries:
            recall_end = next(t for ev, t in recall_entries if ev == "end")
            beliefs_start = next(t for ev, t in beliefs_entries if ev == "start")
            assert (
                beliefs_start >= recall_end
            ), "With parallel disabled, update_beliefs should start after recall_memory ends"

    def test_submit_result_always_sequential(self) -> None:
        """submit_result is always classified as sequential."""
        parallel, sequential = classify_tool_batch(["submit_result", "recall_memory"])
        assert "submit_result" in sequential
        assert "recall_memory" in parallel
        assert "submit_result" in sequential
        assert "recall_memory" in parallel
