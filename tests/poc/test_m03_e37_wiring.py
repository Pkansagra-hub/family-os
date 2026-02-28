"""
tests.poc.test_m03_e37_wiring -- E3.7 End-to-End Wiring Tests.

Validates all 9 issues of Epic 3.7:
  3.7.1 -- Dead-letter for unknown back topics
  3.7.2 -- CancellationToken lifecycle ledger audit
  3.7.3 -- SuspensionManager ledger audit
  3.7.4 -- Parallel tool safety observability (ReactResult counts)
  3.7.5 -- shared.py exports (already done in E3.5, regression only)
  3.7.6 -- Test fixtures update (create_wired_fsm extensions)
  3.7.7 -- M1+M2 regression tests (this file)
  3.7.8 -- Demo smoke tests (separate class)
  3.7.9 -- Documentation (no code, not tested here)

Test count target: ~40 tests.
"""

from __future__ import annotations

import json
import logging
from dataclasses import fields
from typing import Any
from unittest.mock import MagicMock

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import TOPIC_DEAD_LETTER, TOPIC_TASK_CANCEL, TOPIC_TASK_DISPATCH

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


def _make_mock_deps() -> dict[str, Any]:
    """Create mock dependencies for route_back_envelope."""
    bus = MagicMock()
    bus.publish = MagicMock()
    return {
        "model": MagicMock(),
        "ss": MagicMock(),
        "bus": bus,
        "tool_dispatcher": MagicMock(),
        "fsm_state": MagicMock(),
    }


# =========================================================================
# 3.7.1 -- Dead-letter for unknown back topics
# =========================================================================


class TestDeadLetterUnknownBackTopics:
    """Verify route_back_envelope publishes dead-letter for unknown topics."""

    @pytest.mark.asyncio
    async def test_unknown_topic_publishes_dead_letter(self):
        """Unknown topic should publish dead-letter envelope to bus."""
        from poc.k1_poc.actors.back import route_back_envelope

        deps = _make_mock_deps()
        env = _make_envelope(topic="k1.bogus.topic.v1")

        result = await route_back_envelope(envelope=env, **deps)

        assert result is None
        deps["bus"].publish.assert_called_once()
        published = deps["bus"].publish.call_args[0][0]
        assert published.topic == TOPIC_DEAD_LETTER

    @pytest.mark.asyncio
    async def test_unknown_topic_dead_letter_payload(self):
        """Dead-letter payload should contain reason and original topic."""
        from poc.k1_poc.actors.back import route_back_envelope

        deps = _make_mock_deps()
        env = _make_envelope(topic="k1.unknown.v1")

        await route_back_envelope(envelope=env, **deps)

        published = deps["bus"].publish.call_args[0][0]
        payload = json.loads(published.payload)
        assert payload["reason"] == "unknown_back_topic"
        assert payload["original_topic"] == "k1.unknown.v1"

    @pytest.mark.asyncio
    async def test_unknown_topic_dead_letter_has_envelope_id(self):
        """Dead-letter payload should include original envelope_id."""
        from poc.k1_poc.actors.back import route_back_envelope

        deps = _make_mock_deps()
        env = _make_envelope(topic="k1.fake.v1", envelope_id=42)

        await route_back_envelope(envelope=env, **deps)

        published = deps["bus"].publish.call_args[0][0]
        payload = json.loads(published.payload)
        assert payload["envelope_id"] == 42

    @pytest.mark.asyncio
    async def test_empty_topic_publishes_dead_letter(self):
        """Empty string topic should also dead-letter."""
        from poc.k1_poc.actors.back import route_back_envelope

        deps = _make_mock_deps()
        env = _make_envelope(topic="")

        result = await route_back_envelope(envelope=env, **deps)

        assert result is None
        deps["bus"].publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_known_topics_dont_dead_letter(self):
        """Known topics should NOT produce dead-letter (dispatch routes to handler)."""
        from poc.k1_poc.actors.back import route_back_envelope

        deps = _make_mock_deps()
        # back_handler will fail on mock model, but it should NOT dead-letter
        env = _make_envelope(topic=TOPIC_TASK_CANCEL)

        await route_back_envelope(envelope=env, **deps)
        # For cancel topic, no dead-letter should be published
        # (cancel handler is sync and doesn't publish dead-letter)
        published_calls = [
            c
            for c in deps["bus"].publish.call_args_list
            if hasattr(c[0][0], "topic") and c[0][0].topic == TOPIC_DEAD_LETTER
        ]
        assert len(published_calls) == 0

    @pytest.mark.asyncio
    async def test_dead_letter_logs_warning(self, caplog):
        """Unknown topic should produce a warning log."""
        from poc.k1_poc.actors.back import route_back_envelope

        deps = _make_mock_deps()
        env = _make_envelope(topic="k1.mystery.v1")

        with caplog.at_level(logging.WARNING):
            await route_back_envelope(envelope=env, **deps)

        assert any("dead-lettered" in r.message for r in caplog.records)


# =========================================================================
# 3.7.2 -- CancellationToken lifecycle ledger audit
# =========================================================================


class TestCancellationTokenAudit:
    """Verify TaskCancelled enrichment and token lifecycle logging."""

    def test_task_cancelled_has_cancel_reason_field(self):
        """TaskCancelled should have cancel_reason field."""
        from poc.k1_poc.events.task import TaskCancelled

        tc = TaskCancelled(cancel_reason="timeout")
        assert tc.cancel_reason == "timeout"

    def test_task_cancelled_has_had_token_field(self):
        """TaskCancelled should have had_token field."""
        from poc.k1_poc.events.task import TaskCancelled

        tc = TaskCancelled(had_token=True)
        assert tc.had_token is True

    def test_task_cancelled_has_completed_before_cancel(self):
        """TaskCancelled should have completed_before_cancel field."""
        from poc.k1_poc.events.task import TaskCancelled

        tc = TaskCancelled(completed_before_cancel=True)
        assert tc.completed_before_cancel is True

    def test_task_cancelled_to_payload_includes_new_fields(self):
        """to_payload should serialize all enriched fields."""
        from poc.k1_poc.events.task import TaskCancelled

        tc = TaskCancelled(
            cancel_reason="user_requested",
            had_token=True,
            completed_before_cancel=False,
        )
        payload = tc.to_payload()
        assert payload["cancel_reason"] == "user_requested"
        assert payload["had_token"] is True
        assert payload["completed_before_cancel"] is False

    def test_task_cancelled_from_payload_round_trip(self):
        """from_payload should deserialize enriched fields."""
        from poc.k1_poc.events.task import TaskCancelled

        original = TaskCancelled(
            cancel_reason="superseded",
            had_token=True,
            completed_before_cancel=True,
        )
        payload = original.to_payload()
        restored = TaskCancelled.from_payload(payload)
        assert restored.cancel_reason == "superseded"
        assert restored.had_token is True
        assert restored.completed_before_cancel is True

    def test_cancel_handler_register_logs_info(self, caplog):
        """CancellationHandler.register_task should log at INFO."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        with caplog.at_level(logging.INFO):
            handler.register_task("task-99")

        assert any("token created" in r.message and "task-99" in r.message for r in caplog.records)

    def test_cancel_handler_register_returns_token(self):
        """register_task should return a CancellationToken."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler
        from poc.k1_poc.protocols.cancellation import CancellationToken

        handler = CancellationHandler()
        token = handler.register_task("task-42")
        assert isinstance(token, CancellationToken)
        assert token.task_id == "task-42"

    def test_task_cancelled_defaults(self):
        """Default values for enriched fields should be falsy."""
        from poc.k1_poc.events.task import TaskCancelled

        tc = TaskCancelled()
        assert tc.cancel_reason == ""
        assert tc.had_token is False
        assert tc.completed_before_cancel is False


# =========================================================================
# 3.7.3 -- SuspensionManager ledger audit
# =========================================================================


class TestSuspensionManagerAudit:
    """Verify suspension event enrichment and cleanup warning."""

    def test_task_suspended_has_react_history_fields(self):
        """TaskSuspended should have has_react_history and react_history_len."""
        from poc.k1_poc.events.hitl import TaskSuspended

        ts = TaskSuspended(has_react_history=True, react_history_len=5)
        assert ts.has_react_history is True
        assert ts.react_history_len == 5

    def test_task_suspended_to_payload_includes_history_fields(self):
        """to_payload should include react history fields."""
        from poc.k1_poc.events.hitl import TaskSuspended

        ts = TaskSuspended(has_react_history=True, react_history_len=3)
        payload = ts.to_payload()
        assert payload["has_react_history"] is True
        assert payload["react_history_len"] == 3

    def test_task_suspended_from_payload_round_trip(self):
        """from_payload should restore react history fields."""
        from poc.k1_poc.events.hitl import TaskSuspended

        original = TaskSuspended(has_react_history=True, react_history_len=7)
        restored = TaskSuspended.from_payload(original.to_payload())
        assert restored.has_react_history is True
        assert restored.react_history_len == 7

    def test_task_resumed_has_resume_context_field(self):
        """TaskResumed should have has_resume_context field."""
        from poc.k1_poc.events.hitl import TaskResumed

        tr = TaskResumed(has_resume_context=True)
        assert tr.has_resume_context is True

    def test_task_resumed_from_payload_round_trip(self):
        """from_payload should restore has_resume_context."""
        from poc.k1_poc.events.hitl import TaskResumed

        original = TaskResumed(has_resume_context=True, resume_instruction="continue")
        restored = TaskResumed.from_payload(original.to_payload())
        assert restored.has_resume_context is True
        assert restored.resume_instruction == "continue"

    def test_cleanup_task_warns_on_active_context(self, caplog):
        """cleanup_task should warn if active context still exists."""
        from poc.k1_poc.protocols.suspension_manager import SuspensionManager

        mgr = SuspensionManager()
        mgr.store_context("t1", {"question": "what?"})

        with caplog.at_level(logging.WARNING):
            mgr.cleanup_task("t1")

        assert any("leftover state" in r.message and "t1" in r.message for r in caplog.records)

    def test_cleanup_task_no_warn_when_clean(self, caplog):
        """cleanup_task should NOT warn if no context exists."""
        from poc.k1_poc.protocols.suspension_manager import SuspensionManager

        mgr = SuspensionManager()

        with caplog.at_level(logging.WARNING):
            mgr.cleanup_task("t-clean")

        suspension_warns = [r for r in caplog.records if "leftover state" in r.message]
        assert len(suspension_warns) == 0

    def test_cleanup_removes_context(self):
        """cleanup_task should remove stored context."""
        from poc.k1_poc.protocols.suspension_manager import SuspensionManager

        mgr = SuspensionManager()
        mgr.store_context("t1", {"q": "x"})
        mgr.cleanup_task("t1")
        assert mgr.pop_context("t1") is None


# =========================================================================
# 3.7.4 -- Parallel safety observability (ReactResult counts)
# =========================================================================


class TestReactResultObservability:
    """Verify ReactResult has parallel/sequential tool call counters."""

    def test_react_result_has_parallel_count(self):
        """ReactResult should have parallel_tool_calls field."""
        from poc.k1_poc.react.loop import ReactResult

        r = ReactResult(status="complete", parallel_tool_calls=3)
        assert r.parallel_tool_calls == 3

    def test_react_result_has_sequential_count(self):
        """ReactResult should have sequential_tool_calls field."""
        from poc.k1_poc.react.loop import ReactResult

        r = ReactResult(status="complete", sequential_tool_calls=5)
        assert r.sequential_tool_calls == 5

    def test_react_result_default_counts_zero(self):
        """Default parallel/sequential counts should be 0."""
        from poc.k1_poc.react.loop import ReactResult

        r = ReactResult(status="complete")
        assert r.parallel_tool_calls == 0
        assert r.sequential_tool_calls == 0

    def test_react_result_field_names(self):
        """ReactResult dataclass should have the expected field set."""
        from poc.k1_poc.react.loop import ReactResult

        field_names = {f.name for f in fields(ReactResult)}
        assert "parallel_tool_calls" in field_names
        assert "sequential_tool_calls" in field_names
        assert "dispatched_tasks" in field_names
        assert "status" in field_names


# =========================================================================
# 3.7.5 -- shared.py exports (regression)
# =========================================================================


class TestSharedExportsRegression:
    """Verify shared.py utilities remain importable (E3.5 regression)."""

    def test_parse_envelope_payload_importable(self):
        from poc.k1_poc.actors.shared import parse_envelope_payload

        assert callable(parse_envelope_payload)

    def test_safe_get_section_importable(self):
        from poc.k1_poc.actors.shared import safe_get_section

        assert callable(safe_get_section)

    def test_never_cancel_importable(self):
        from poc.k1_poc.actors.shared import never_cancel

        assert callable(never_cancel)

    def test_actors_package_exports_shared(self):
        """__init__.py should re-export shared utilities."""
        from poc.k1_poc.actors import never_cancel, parse_envelope_payload, safe_get_section

        assert callable(parse_envelope_payload)
        assert callable(safe_get_section)
        assert callable(never_cancel)


# =========================================================================
# 3.7.6 -- Test fixtures update
# =========================================================================


class TestFixturesUpdate:
    """Verify extended test fixtures for M3."""

    def test_create_wired_fsm_with_cancel_tokens(self):
        """create_wired_fsm(with_cancel_tokens=True) should expose cancel_handler."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        components = create_wired_fsm(with_cancel_tokens=True)
        assert "cancel_handler" in components
        assert components["cancel_handler"] is not None

    def test_create_wired_fsm_without_cancel_tokens(self):
        """create_wired_fsm() default should NOT expose cancel_handler."""
        from poc.k1_poc.testing.fixtures import create_wired_fsm

        components = create_wired_fsm()
        assert "cancel_handler" not in components

    def test_create_test_cancel_token(self):
        """create_test_cancel_token should return a working token."""
        from poc.k1_poc.testing.fixtures import create_test_cancel_token

        token = create_test_cancel_token("my-task")
        assert token.task_id == "my-task"
        assert not token.is_cancelled

    def test_invoke_back_handler_importable(self):
        """invoke_back_handler should be importable."""
        from poc.k1_poc.testing.fixtures import invoke_back_handler

        assert callable(invoke_back_handler)

    def test_invoke_back_router_importable(self):
        """invoke_back_router should be importable."""
        from poc.k1_poc.testing.fixtures import invoke_back_router

        assert callable(invoke_back_router)

    def test_fixtures_all_exports(self):
        """__all__ should include new fixture helpers."""
        from poc.k1_poc.testing import fixtures

        expected = {
            "create_test_cancel_token",
            "invoke_back_handler",
            "invoke_back_router",
        }
        assert expected.issubset(set(fixtures.__all__))


# =========================================================================
# 3.7.8 -- Demo coordinator health check (parallel_tools)
# =========================================================================


class TestDemoHealthCheck:
    """Verify coordinator health check includes parallel_tools."""

    @pytest.mark.asyncio
    async def test_coordinator_health_check_has_parallel_tools(self):
        """_phase5_health_check should check parallel_tools_configured."""
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        coord = K1DemoCoordinator(test_mode=True)
        # Minimal setup for health check to run
        coord.bus = MagicMock()
        coord.model = MagicMock()
        coord.session_state = MagicMock()
        coord.capability_registry = None
        coord.output_channel = None
        coord.iot_stubs = None
        coord.ledger = None
        coord.ledger_store = None
        coord.dead_letter_consumer = None
        coord.fsm = None

        await coord._phase5_health_check()

        # Check that parallel_tools was checked in timeline
        timeline_events = [e.event for e in coord._timeline]
        assert "check.parallel_tools" in timeline_events

    @pytest.mark.asyncio
    async def test_coordinator_parallel_tools_check_passes(self):
        """parallel_tools_configured check should be True (non-fatal)."""
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        coord = K1DemoCoordinator(test_mode=True)
        coord.bus = MagicMock()
        coord.model = MagicMock()
        coord.session_state = MagicMock()
        coord.capability_registry = None
        coord.output_channel = None
        coord.iot_stubs = None
        coord.ledger = None
        coord.ledger_store = None
        coord.dead_letter_consumer = None
        coord.fsm = None

        await coord._phase5_health_check()

        # Find the parallel_tools entry in timeline
        pt_entries = [e for e in coord._timeline if e.event == "check.parallel_tools"]
        assert len(pt_entries) == 1
        assert (
            "parallel tools" in pt_entries[0].summary.lower()
            or "Parallel tools" in pt_entries[0].summary
        )
