"""
tests.poc.test_m03_e33_resume_context -- E3.3 Resume Context Canonicalization.

Validates the 5 issues of Epic 3.3:
  3.3.1 -- SuspensionManager elected as single resume-context owner
  3.3.2 -- back_resume_handler uses envelope-carried resume context
  3.3.3 -- store_pending_context / _get/_clear deprecated
  3.3.4 -- _emit_back_result includes react_history in suspended payload
  3.3.5 -- SuspensionManager.cleanup_task called on terminal states

Test count target: ~35 tests.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.topics import TOPIC_TASK_DISPATCH, TOPIC_TASK_RESUME
from k1.concierge.llm.types import ModelMessage
from k1.concierge.react.loop import ReactResult

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


def _make_messages() -> list[ModelMessage]:
    """Build a short message list for testing serialization."""
    return [
        ModelMessage(role="user", content="Find a restaurant"),
        ModelMessage(role="assistant", content="Searching..."),
        ModelMessage(
            role="tool",
            content='{"result": "found"}',
            tool_call_id="tc_1",
            name="recall_memory",
        ),
    ]


# =========================================================================
# 3.3.1 -- SuspensionManager elected as single resume-context owner
# =========================================================================


class TestSuspensionManagerSingleOwner:
    """Verify SuspensionManager is the canonical resume-context owner."""

    def test_suspension_manager_has_store_context(self):
        """SuspensionManager.store_context exists and stores data."""
        from k1.hil.suspension import SuspensionManager

        mgr = SuspensionManager()
        mgr.store_context("t1", {"react_history": [], "original_task": {"action": "test"}})

        assert mgr.has_context("t1")

    def test_suspension_manager_pop_context(self):
        """SuspensionManager.pop_context retrieves and removes."""
        from k1.hil.suspension import SuspensionManager

        mgr = SuspensionManager()
        mgr.store_context("t1", {"key": "value"})
        ctx = mgr.pop_context("t1")

        assert ctx == {"key": "value"}
        assert not mgr.has_context("t1")

    def test_back_resume_handler_reads_from_resume_context(self):
        """back_resume_handler extracts original_task from envelope resume_context."""
        import inspect

        from k1.concierge.actors.back import back_resume_handler

        source = inspect.getsource(back_resume_handler)
        # Primary path reads from resume_context
        assert 'resume_context.get("original_task"' in source
        assert 'resume_context.get("react_history"' in source

    def test_fsm_on_task_suspended_stores_via_suspension_manager(self):
        """FSM _on_task_suspended calls suspension_manager.store_context."""
        import inspect

        from k1.concierge.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_suspended)
        assert "store_context" in source


# =========================================================================
# 3.3.2 -- back_resume_handler uses envelope-carried resume context
# =========================================================================


class TestResumeHandlerEnvelopeContext:
    """Verify back_resume_handler reads from envelope payload."""

    @pytest.mark.asyncio
    async def test_primary_path_uses_resume_context(self):
        """When resume_context has data, handler uses it (not _get_pending_context)."""
        from k1.concierge.actors.back import back_resume_handler

        messages = _make_messages()
        from k1.concierge.actors.back import _serialize_messages

        serialized = _serialize_messages(messages)

        resume_ctx = {
            "original_task": {"task_id": "t1", "action": "find_restaurant", "tier": "LOW"},
            "react_history": serialized,
            "instruction": "Resume from prior context.",
        }

        env = _make_envelope(
            topic=TOPIC_TASK_RESUME,
            payload={
                "task_id": "t1",
                "resolution": {"answer": "Italian"},
                "resume_context": resume_ctx,
            },
        )

        mock_model = AsyncMock()
        mock_bus = MagicMock()
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = None
        mock_td = MagicMock()

        result = ReactResult(status="complete", data={"final_answer": "done"})

        with patch(
            "k1.concierge.actors.back.react_loop", new_callable=AsyncMock, return_value=result
        ):
            with patch("k1.concierge.actors.back._emit_back_result"):
                with patch("k1.concierge.actors.back._clear_pending_context"):
                    res = await back_resume_handler(
                        envelope=env,
                        model=mock_model,
                        ss=mock_ss,
                        bus=mock_bus,
                        tool_dispatcher=mock_td,
                    )

        assert res.status == "complete"

    @pytest.mark.asyncio
    async def test_fallback_to_get_pending_context(self):
        """When resume_context is empty, falls back to _get_pending_context."""
        from k1.concierge.actors.back import back_resume_handler

        env = _make_envelope(
            topic=TOPIC_TASK_RESUME,
            payload={
                "task_id": "t1",
                "resolution": {"answer": "test"},
            },
        )

        # FSM state with pending_context (legacy path)
        fsm = MagicMock()
        fsm.pending_context = {
            "t1": {
                "original_task": {"task_id": "t1", "tier": "LOW"},
                "prior_messages": [ModelMessage(role="user", content="test")],
            }
        }

        mock_model = AsyncMock()
        mock_bus = MagicMock()
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = None
        mock_td = MagicMock()

        result = ReactResult(status="complete", data={"final_answer": "done"})

        with patch(
            "k1.concierge.actors.back.react_loop", new_callable=AsyncMock, return_value=result
        ):
            with patch("k1.concierge.actors.back._emit_back_result"):
                with patch("k1.concierge.actors.back._clear_pending_context"):
                    res = await back_resume_handler(
                        envelope=env,
                        model=mock_model,
                        ss=mock_ss,
                        bus=mock_bus,
                        tool_dispatcher=mock_td,
                        fsm_state=fsm,
                    )

        assert res.status == "complete"

    @pytest.mark.asyncio
    async def test_no_context_emits_failed(self):
        """When neither resume_context nor pending_context available, emits failed."""
        from k1.concierge.actors.back import back_resume_handler

        env = _make_envelope(
            topic=TOPIC_TASK_RESUME,
            payload={
                "task_id": "t1",
                "resolution": {"answer": "test"},
            },
        )

        mock_bus = MagicMock()

        res = await back_resume_handler(
            envelope=env,
            model=AsyncMock(),
            ss=MagicMock(),
            bus=mock_bus,
            tool_dispatcher=MagicMock(),
            fsm_state=None,
        )

        assert res.status == "cancelled"
        assert res.data["reason"] == "no_pending_context"
        mock_bus.publish.assert_called_once()


# =========================================================================
# 3.3.3 -- Deprecation of old context helpers
# =========================================================================


class TestDeprecatedContextHelpers:
    """Verify old context helpers are deprecated."""

    def test_store_pending_context_has_deprecation_notice(self):
        """store_pending_context docstring mentions deprecated."""
        from k1.concierge.actors.back import store_pending_context

        assert "deprecated" in store_pending_context.__doc__.lower()

    def test_get_pending_context_has_deprecation_notice(self):
        """_get_pending_context docstring mentions deprecated."""
        from k1.concierge.actors.back import _get_pending_context

        assert "deprecated" in _get_pending_context.__doc__.lower()

    def test_clear_pending_context_has_deprecation_notice(self):
        """_clear_pending_context docstring mentions deprecated."""
        from k1.concierge.actors.back import _clear_pending_context

        assert "deprecated" in _clear_pending_context.__doc__.lower()

    def test_store_pending_context_has_removal_comment(self):
        """store_pending_context source has TODO: Remove in M8."""
        import inspect

        from k1.concierge.actors.back import store_pending_context

        source = inspect.getsource(store_pending_context)
        assert "Remove in M8" in source

    def test_get_pending_context_has_removal_comment(self):
        """_get_pending_context source has TODO: Remove in M8."""
        import inspect

        from k1.concierge.actors.back import _get_pending_context

        source = inspect.getsource(_get_pending_context)
        assert "Remove in M8" in source

    def test_clear_pending_context_has_removal_comment(self):
        """_clear_pending_context source has TODO: Remove in M8."""
        import inspect

        from k1.concierge.actors.back import _clear_pending_context

        source = inspect.getsource(_clear_pending_context)
        assert "Remove in M8" in source

    def test_store_pending_context_still_works(self):
        """Deprecated store_pending_context still functions for backward compat."""
        from k1.concierge.actors.back import store_pending_context

        fsm = MagicMock()
        fsm.pending_context = {}

        store_pending_context(
            fsm_state=fsm,
            task_id="t1",
            original_task={"action": "test"},
            prior_messages=[ModelMessage(role="user", content="hi")],
        )

        assert "t1" in fsm.pending_context
        assert fsm.pending_context["t1"]["original_task"]["action"] == "test"


# =========================================================================
# 3.3.4 -- _emit_back_result includes react_history in suspended payload
# =========================================================================


class TestEmitBackResultReactHistory:
    """Verify _emit_back_result includes react_history for suspended status."""

    def test_suspended_includes_react_history(self):
        """Suspended payload includes serialized react_history."""
        from k1.concierge.actors.back import _emit_back_result

        bus = MagicMock()
        env = _make_envelope(payload={"task_id": "t1", "action": "test"})
        messages = _make_messages()

        result = ReactResult(
            status="suspended",
            data={
                "hil_type": "clarification",
                "question": "Which type?",
            },
        )

        _emit_back_result(
            bus,
            env,
            "t1",
            result,
            react_history=messages,
            original_task={"task_id": "t1", "action": "test"},
        )

        bus.publish.assert_called_once()
        published_env = bus.publish.call_args[0][0]
        payload = json.loads(published_env.payload)

        assert "react_history" in payload
        assert len(payload["react_history"]) == 3
        assert payload["react_history"][0]["role"] == "user"
        assert payload["react_history"][0]["content"] == "Find a restaurant"

    def test_suspended_includes_original_task(self):
        """Suspended payload includes original_task."""
        from k1.concierge.actors.back import _emit_back_result

        bus = MagicMock()
        env = _make_envelope(payload={"task_id": "t1"})
        task = {"task_id": "t1", "action": "book", "tier": "HIGH"}

        result = ReactResult(
            status="suspended",
            data={"hil_type": "approval", "question": "Proceed?"},
        )

        _emit_back_result(
            bus,
            env,
            "t1",
            result,
            react_history=[],
            original_task=task,
        )

        published_env = bus.publish.call_args[0][0]
        payload = json.loads(published_env.payload)

        assert payload["original_task"] == task

    def test_suspended_without_history_has_no_react_history_key(self):
        """Without react_history param, suspended payload omits the key."""
        from k1.concierge.actors.back import _emit_back_result

        bus = MagicMock()
        env = _make_envelope(payload={"task_id": "t1"})

        result = ReactResult(
            status="suspended",
            data={"hil_type": "clarification", "question": "What?"},
        )

        _emit_back_result(bus, env, "t1", result)

        published_env = bus.publish.call_args[0][0]
        payload = json.loads(published_env.payload)

        assert "react_history" not in payload
        assert "original_task" not in payload

    def test_complete_status_ignores_react_history(self):
        """Complete status does not include react_history even if provided."""
        from k1.concierge.actors.back import _emit_back_result

        bus = MagicMock()
        env = _make_envelope(payload={"task_id": "t1"})
        messages = _make_messages()

        result = ReactResult(
            status="complete",
            data={"final_answer": "Done", "results": []},
        )

        _emit_back_result(
            bus,
            env,
            "t1",
            result,
            react_history=messages,
            original_task={"task_id": "t1"},
        )

        published_env = bus.publish.call_args[0][0]
        payload = json.loads(published_env.payload)

        # Complete payload should NOT have react_history
        assert "react_history" not in payload


# =========================================================================
# 3.3.4 -- Message serialization/deserialization
# =========================================================================


class TestMessageSerialization:
    """Verify _serialize_messages and _deserialize_messages round-trip."""

    def test_serialize_basic_messages(self):
        """Serialize user/assistant/tool messages to dicts."""
        from k1.concierge.actors.back import _serialize_messages

        messages = _make_messages()
        serialized = _serialize_messages(messages)

        assert len(serialized) == 3
        assert serialized[0] == {"role": "user", "content": "Find a restaurant"}
        assert serialized[1] == {"role": "assistant", "content": "Searching..."}
        assert serialized[2]["role"] == "tool"
        assert serialized[2]["tool_call_id"] == "tc_1"
        assert serialized[2]["name"] == "recall_memory"

    def test_deserialize_basic_messages(self):
        """Deserialize dicts back to ModelMessage list."""
        from k1.concierge.actors.back import _deserialize_messages

        data = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "tool", "content": "{}", "tool_call_id": "tc_1", "name": "recall_memory"},
        ]

        messages = _deserialize_messages(data)

        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[2].tool_call_id == "tc_1"
        assert messages[2].name == "recall_memory"

    def test_roundtrip_preserves_data(self):
        """Serialize then deserialize preserves role/content/tool_call_id/name."""
        from k1.concierge.actors.back import _deserialize_messages, _serialize_messages

        original = _make_messages()
        serialized = _serialize_messages(original)
        restored = _deserialize_messages(serialized)

        for orig, rest in zip(original, restored):
            assert orig.role == rest.role
            assert orig.content == rest.content
            assert orig.tool_call_id == rest.tool_call_id
            assert orig.name == rest.name

    def test_serialize_empty_list(self):
        """Serialize empty list returns empty list."""
        from k1.concierge.actors.back import _serialize_messages

        assert _serialize_messages([]) == []

    def test_deserialize_empty_list(self):
        """Deserialize empty list returns empty list."""
        from k1.concierge.actors.back import _deserialize_messages

        assert _deserialize_messages([]) == []


# =========================================================================
# 3.3.5 -- SuspensionManager.cleanup_task on terminal states
# =========================================================================


class TestCleanupTaskOnTerminalStates:
    """Verify FSM calls cleanup_task on task complete/failed/cancel."""

    def test_on_task_complete_calls_cleanup_task(self):
        """_on_task_complete source calls suspension_manager.cleanup_task."""
        import inspect

        from k1.concierge.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_complete)
        assert "cleanup_task" in source

    def test_on_task_failed_calls_cleanup_task(self):
        """_on_task_failed source calls suspension_manager.cleanup_task."""
        import inspect

        from k1.concierge.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_failed)
        assert "cleanup_task" in source

    def test_on_task_cancel_calls_cleanup_task(self):
        """_on_task_cancel source calls suspension_manager.cleanup_task."""
        import inspect

        from k1.concierge.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_cancel)
        assert "cleanup_task" in source

    def test_cleanup_task_removes_contexts(self):
        """SuspensionManager.cleanup_task removes stored context."""
        from k1.hil.suspension import SuspensionManager

        mgr = SuspensionManager()
        mgr.store_context("t1", {"data": "test"})
        assert mgr.has_context("t1")

        mgr.cleanup_task("t1")
        assert not mgr.has_context("t1")

    def test_cleanup_task_removes_suspension_counts(self):
        """SuspensionManager.cleanup_task clears suspension counts."""
        from k1.hil.suspension import SuspensionManager

        mgr = SuspensionManager()
        mgr._suspension_counts["t1"] = 2
        mgr.cleanup_task("t1")
        assert "t1" not in mgr._suspension_counts

    def test_cleanup_task_idempotent(self):
        """cleanup_task on unknown task does not raise."""
        from k1.hil.suspension import SuspensionManager

        mgr = SuspensionManager()
        mgr.cleanup_task("t_nonexistent")  # Should not raise


# =========================================================================
# Integration: Full resume flow via SuspensionManager
# =========================================================================


class TestResumeFlowIntegration:
    """Integration tests for the unified resume context flow."""

    def test_suspended_payload_flows_through_store_and_pop(self):
        """Simulates: Back emits suspended (with history) -> FSM stores -> FSM pops."""
        from k1.concierge.actors.back import _serialize_messages
        from k1.hil.suspension import SuspensionManager

        messages = _make_messages()
        serialized = _serialize_messages(messages)

        # Simulate suspended payload (as built by _emit_back_result)
        suspended_payload = {
            "task_id": "t1",
            "hil_type": "clarification",
            "question": "Which type?",
            "react_history": serialized,
            "original_task": {"task_id": "t1", "action": "find", "tier": "LOW"},
        }

        # FSM stores it
        mgr = SuspensionManager()
        mgr.store_context("t1", suspended_payload)

        # FSM pops on resume
        stored = mgr.pop_context("t1")
        assert stored is not None
        assert stored["react_history"] == serialized
        assert stored["original_task"]["action"] == "find"

    @pytest.mark.asyncio
    async def test_end_to_end_resume_with_envelope_context(self):
        """Full flow: envelope has resume_context -> handler uses it."""
        from k1.concierge.actors.back import _serialize_messages, back_resume_handler

        messages = _make_messages()
        serialized = _serialize_messages(messages)

        resume_ctx = {
            "original_task": {"task_id": "t1", "action": "book", "tier": "MEDIUM"},
            "react_history": serialized,
            "instruction": "User answered: Italian food",
            "hil_type": "clarification",
        }

        env = _make_envelope(
            topic=TOPIC_TASK_RESUME,
            payload={
                "task_id": "t1",
                "resolution": {"additional_info": "Italian"},
                "resume_context": resume_ctx,
            },
        )

        mock_result = ReactResult(status="complete", data={"final_answer": "Booked"})
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = None

        with patch(
            "k1.concierge.actors.back.react_loop",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_loop:
            with patch("k1.concierge.actors.back._emit_back_result"):
                with patch("k1.concierge.actors.back._clear_pending_context"):
                    result = await back_resume_handler(
                        envelope=env,
                        model=AsyncMock(),
                        ss=mock_ss,
                        bus=MagicMock(),
                        tool_dispatcher=MagicMock(),
                    )

        assert result.status == "complete"

        # Verify react_loop was called with deserialized messages
        call_kwargs = mock_loop.call_args[1]
        assert call_kwargs["scenario"] == "task_resume"
        # Messages should include prior history + resume instruction
        msgs = call_kwargs["messages"]
        # 3 deserialized + 1 resume instruction = 4
        assert len(msgs) == 4
        assert msgs[0].role == "user"
        assert msgs[0].content == "Find a restaurant"
