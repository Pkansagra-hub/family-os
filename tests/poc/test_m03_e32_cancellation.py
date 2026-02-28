"""
tests.poc.test_m03_e32_cancellation -- E3.2 Mandatory Cancellation Propagation.

Validates the 5 issues of Epic 3.2:
  3.2.1 -- fsm_state passed to back handlers (verified in E3.1 wiring tests)
  3.2.2 -- CancellationToken per task dispatch (FSM already does this)
  3.2.3 -- _build_cancellation_check uses CancellationToken
  3.2.4 -- back_cancel_handler uses CancellationToken API
  3.2.5 -- cancel_token parameter in handler signatures

Test count target: ~35 tests.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import TOPIC_TASK_CANCEL, TOPIC_TASK_DISPATCH
from poc.k1_poc.protocols.cancellation import CancellationToken, CancelReason, TaskCancelledError

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


def _make_fsm_with_token(task_id: str = "t1") -> tuple[MagicMock, CancellationToken]:
    """Create a mock FSM with a real CancellationToken registered."""
    from poc.k1_poc.protocols.cancel_handler import CancellationHandler

    handler = CancellationHandler()
    token = handler.register_task(task_id)  # noqa: F841

    fsm = MagicMock()
    fsm.cancel_handler = handler
    return fsm, token


# =========================================================================
# 3.2.1 -- fsm_state passed to back handlers
# =========================================================================


class TestFSMStatePassedToHandlers:
    """Verify fsm_state is passed through the routing chain."""

    def test_coordinator_passes_fsm_state(self):
        """coordinator._run_back_handler passes fsm_state kwarg."""
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator._run_back_handler)
        # M7 E7.3.3: fsm_state is now passed via call_kwargs dict
        assert "fsm_state" in source

    def test_bootstrap_passes_fsm_state(self):
        """bootstrap._mailbox_consumer passes fsm_state kwarg."""
        import inspect

        from poc.k1_poc.kernel.bootstrap import _mailbox_consumer

        source = inspect.getsource(_mailbox_consumer)
        assert "fsm_state=" in source


# =========================================================================
# 3.2.2 -- CancellationToken per task dispatch
# =========================================================================


class TestCancellationTokenPerDispatch:
    """Verify CancellationHandler creates per-task tokens."""

    def test_register_task_creates_token(self):
        """CancellationHandler.register_task returns a CancellationToken."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        token = handler.register_task("t1")

        assert isinstance(token, CancellationToken)
        assert token.task_id == "t1"
        assert not token.is_cancelled

    def test_register_task_stores_token(self):
        """CancellationHandler.get_token retrieves registered token."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        token = handler.register_task("t1")

        retrieved = handler.get_token("t1")
        assert retrieved is token

    def test_request_cancel_sets_token(self):
        """CancellationHandler.request_cancel cancels the per-task token."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        handler.register_task("t1")
        handler.request_cancel("t1")

        token = handler.get_token("t1")
        assert token is not None
        assert token.is_cancelled
        assert token.cancel_reason == CancelReason.USER_REQUESTED

    def test_multiple_tasks_independent(self):
        """Cancelling one task does not cancel another."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        handler.register_task("t1")
        handler.register_task("t2")
        handler.request_cancel("t1")

        t1 = handler.get_token("t1")
        t2 = handler.get_token("t2")
        assert t1 is not None and t1.is_cancelled
        assert t2 is not None and not t2.is_cancelled

    def test_fsm_controller_calls_register_task(self):
        """ConciergeController._on_task_dispatch calls register_task."""
        import inspect

        from poc.k1_poc.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_dispatch)
        assert "register_task" in source

    def test_fsm_controller_calls_request_cancel(self):
        """ConciergeController._on_task_cancel calls request_cancel."""
        import inspect

        from poc.k1_poc.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_cancel)
        assert "request_cancel" in source


# =========================================================================
# 3.2.3 -- _build_cancellation_check uses CancellationToken
# =========================================================================


class TestBuildCancellationCheck:
    """Verify _build_cancellation_check uses CancellationToken."""

    @pytest.mark.asyncio
    async def test_with_token_not_cancelled(self):
        """Token not cancelled -> check returns False."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        token = CancellationToken(task_id="t1")
        check = _build_cancellation_check(cancel_token=token)
        result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_with_token_cancelled(self):
        """Token cancelled -> check returns True."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        token = CancellationToken(task_id="t1")
        token.cancel(CancelReason.USER_REQUESTED)
        check = _build_cancellation_check(cancel_token=token)
        result = await check()
        assert result is True

    @pytest.mark.asyncio
    async def test_with_token_cancel_after_build(self):
        """Token cancelled AFTER building check -> next call returns True."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        token = CancellationToken(task_id="t1")
        check = _build_cancellation_check(cancel_token=token)

        assert await check() is False
        token.cancel(CancelReason.TIMEOUT)
        assert await check() is True

    @pytest.mark.asyncio
    async def test_legacy_fallback_with_fsm_state(self):
        """No token but fsm_state with cancellation_requested -> True."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        fsm = MagicMock()
        fsm.cancellation_requested = True
        check = _build_cancellation_check(cancel_token=None, fsm_state=fsm)
        result = await check()
        assert result is True

    @pytest.mark.asyncio
    async def test_legacy_fallback_not_cancelled(self):
        """No token, fsm_state.cancellation_requested=False -> False."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        fsm = MagicMock()
        fsm.cancellation_requested = False
        check = _build_cancellation_check(cancel_token=None, fsm_state=fsm)
        result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_no_token_no_fsm(self):
        """No token, no fsm_state -> _never_cancel (always False)."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        check = _build_cancellation_check(cancel_token=None, fsm_state=None)
        result = await check()
        assert result is False

    @pytest.mark.asyncio
    async def test_token_takes_priority_over_fsm(self):
        """When both token and fsm_state provided, token wins."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        token = CancellationToken(task_id="t1")
        fsm = MagicMock()
        fsm.cancellation_requested = True  # fsm says cancel

        # Token says NOT cancelled -- token should win
        check = _build_cancellation_check(cancel_token=token, fsm_state=fsm)
        result = await check()
        assert result is False  # Token wins


# =========================================================================
# 3.2.3 -- _extract_cancel_token helper
# =========================================================================


class TestExtractCancelToken:
    """Verify _extract_cancel_token extracts tokens from FSM."""

    def test_extract_from_cancel_handler_property(self):
        """Extracts token via fsm_state.cancel_handler.get_token()."""
        from poc.k1_poc.actors.back import _extract_cancel_token

        fsm, token = _make_fsm_with_token("t1")
        extracted = _extract_cancel_token(fsm, "t1")
        assert extracted is token

    def test_returns_none_for_unknown_task(self):
        """Returns None when task_id not registered."""
        from poc.k1_poc.actors.back import _extract_cancel_token

        fsm, _ = _make_fsm_with_token("t1")
        extracted = _extract_cancel_token(fsm, "t_unknown")
        assert extracted is None

    def test_returns_none_for_none_fsm(self):
        """Returns None when fsm_state is None."""
        from poc.k1_poc.actors.back import _extract_cancel_token

        extracted = _extract_cancel_token(None, "t1")
        assert extracted is None

    def test_returns_none_for_empty_task_id(self):
        """Returns None when task_id is empty."""
        from poc.k1_poc.actors.back import _extract_cancel_token

        fsm, _ = _make_fsm_with_token("t1")
        extracted = _extract_cancel_token(fsm, "")
        assert extracted is None

    def test_returns_none_for_fsm_without_handler(self):
        """Returns None when fsm_state has no cancel_handler."""
        from poc.k1_poc.actors.back import _extract_cancel_token

        fsm = MagicMock(spec=[])  # No attributes
        extracted = _extract_cancel_token(fsm, "t1")
        assert extracted is None


# =========================================================================
# 3.2.4 -- back_cancel_handler uses CancellationToken
# =========================================================================


class TestBackCancelHandlerToken:
    """Verify back_cancel_handler uses CancellationToken API."""

    def test_cancel_with_token(self):
        """back_cancel_handler calls token.cancel() when token provided."""
        from poc.k1_poc.actors.back import back_cancel_handler

        token = CancellationToken(task_id="t1")
        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        back_cancel_handler(envelope=env, cancel_token=token)

        assert token.is_cancelled
        assert token.cancel_reason == CancelReason.USER_REQUESTED

    def test_cancel_idempotent(self):
        """Calling cancel twice via handler is idempotent."""
        from poc.k1_poc.actors.back import back_cancel_handler

        token = CancellationToken(task_id="t1")
        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        back_cancel_handler(envelope=env, cancel_token=token)
        back_cancel_handler(envelope=env, cancel_token=token)

        assert token.is_cancelled

    def test_cancel_extracts_from_fsm(self):
        """back_cancel_handler extracts token from fsm_state if not provided."""
        from poc.k1_poc.actors.back import back_cancel_handler

        fsm, token = _make_fsm_with_token("t1")
        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        back_cancel_handler(envelope=env, fsm_state=fsm)

        assert token.is_cancelled

    def test_cancel_legacy_fallback(self):
        """back_cancel_handler falls back to raw bool when no token available."""
        from poc.k1_poc.actors.back import back_cancel_handler

        fsm = MagicMock()
        fsm.cancellation_requested = False
        fsm.cancelled_tasks = set()
        # Make sure cancel_handler returns no token
        del fsm.cancel_handler
        fsm._cancel_handler = None

        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        back_cancel_handler(envelope=env, fsm_state=fsm)

        assert fsm.cancellation_requested is True
        assert "t1" in fsm.cancelled_tasks

    def test_cancel_no_fsm_no_token_warns(self):
        """back_cancel_handler with no fsm_state or token warns but no crash."""
        from poc.k1_poc.actors.back import back_cancel_handler

        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        # Should not raise
        back_cancel_handler(envelope=env, fsm_state=None, cancel_token=None)

    def test_no_direct_fsm_state_mutation_with_token(self):
        """When token is available, fsm_state attributes are NOT mutated."""
        from poc.k1_poc.actors.back import back_cancel_handler

        fsm, token = _make_fsm_with_token("t1")
        fsm.cancellation_requested = False
        fsm.cancelled_tasks = set()

        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        back_cancel_handler(envelope=env, fsm_state=fsm, cancel_token=token)

        # Token used, NOT the raw boolean
        assert token.is_cancelled
        assert fsm.cancellation_requested is False  # NOT mutated
        assert "t1" not in fsm.cancelled_tasks  # NOT mutated


# =========================================================================
# 3.2.5 -- cancel_token in handler signatures
# =========================================================================


class TestCancelTokenSignature:
    """Verify all back handlers accept cancel_token parameter."""

    def test_back_handler_has_cancel_token_param(self):
        """back_handler has cancel_token in signature."""
        import inspect

        from poc.k1_poc.actors.back import back_handler

        sig = inspect.signature(back_handler)
        assert "cancel_token" in sig.parameters
        # Default is None (optional for backward compat)
        assert sig.parameters["cancel_token"].default is None

    def test_back_resume_handler_has_cancel_token_param(self):
        """back_resume_handler has cancel_token in signature."""
        import inspect

        from poc.k1_poc.actors.back import back_resume_handler

        sig = inspect.signature(back_resume_handler)
        assert "cancel_token" in sig.parameters
        assert sig.parameters["cancel_token"].default is None

    def test_back_cancel_handler_has_cancel_token_param(self):
        """back_cancel_handler has cancel_token in signature."""
        import inspect

        from poc.k1_poc.actors.back import back_cancel_handler

        sig = inspect.signature(back_cancel_handler)
        assert "cancel_token" in sig.parameters
        assert sig.parameters["cancel_token"].default is None

    def test_route_back_envelope_extracts_token(self):
        """route_back_envelope source extracts cancel_token from fsm_state."""
        import inspect

        from poc.k1_poc.actors.back import route_back_envelope

        source = inspect.getsource(route_back_envelope)
        assert "_extract_cancel_token" in source
        assert "cancel_token=" in source

    def test_cancel_token_type_annotation(self):
        """back_handler cancel_token is typed as CancellationToken | None."""
        import inspect

        from poc.k1_poc.actors.back import back_handler

        sig = inspect.signature(back_handler)
        annotation = str(sig.parameters["cancel_token"].annotation)
        assert "CancellationToken" in annotation


# =========================================================================
# Integration: CancellationToken flows end-to-end
# =========================================================================


class TestCancellationTokenEndToEnd:
    """Integration tests for per-task cancellation flow."""

    def test_token_check_raises_cancelled_error(self):
        """CancellationToken.check() raises TaskCancelledError when cancelled."""
        token = CancellationToken(task_id="t1")
        token.cancel(CancelReason.USER_REQUESTED)

        with pytest.raises(TaskCancelledError):
            token.check()

    def test_token_check_passes_when_not_cancelled(self):
        """CancellationToken.check() does NOT raise when not cancelled."""
        token = CancellationToken(task_id="t1")
        token.check()  # Should not raise

    @pytest.mark.asyncio
    async def test_cancel_token_flows_through_route_back_envelope(self):
        """route_back_envelope passes cancel_token from FSM to handler."""
        from unittest.mock import AsyncMock, patch

        from poc.k1_poc.actors.back import route_back_envelope

        fsm, token = _make_fsm_with_token("t1")
        env = _make_envelope(
            topic=TOPIC_TASK_DISPATCH,
            payload={"task_id": "t1"},
        )

        with patch(
            "poc.k1_poc.actors.back.back_handler",
            new_callable=AsyncMock,
        ) as mock_bh:
            await route_back_envelope(
                envelope=env,
                model=MagicMock(),
                ss=MagicMock(),
                bus=MagicMock(),
                tool_dispatcher=MagicMock(),
                fsm_state=fsm,
            )

        mock_bh.assert_called_once()
        call_kwargs = mock_bh.call_args[1]
        assert call_kwargs["cancel_token"] is token

    @pytest.mark.asyncio
    async def test_cancel_propagates_to_back_handler_check(self):
        """Cancelling token makes _build_cancellation_check return True."""
        from poc.k1_poc.actors.back import _build_cancellation_check

        token = CancellationToken(task_id="t1")
        check = _build_cancellation_check(cancel_token=token)

        # Not cancelled yet
        assert await check() is False

        # Cancel the token (simulates FSM receiving task.cancel)
        token.cancel(CancelReason.USER_REQUESTED)

        # Now check returns True
        assert await check() is True

    @pytest.mark.asyncio
    async def test_cancel_token_flows_for_cancel_topic(self):
        """route_back_envelope passes cancel_token for task.cancel topic."""
        from unittest.mock import patch

        from poc.k1_poc.actors.back import route_back_envelope

        fsm, token = _make_fsm_with_token("t1")
        env = _make_envelope(
            topic=TOPIC_TASK_CANCEL,
            payload={"task_id": "t1"},
        )

        with patch(
            "poc.k1_poc.actors.back.back_cancel_handler",
        ) as mock_bch:
            await route_back_envelope(
                envelope=env,
                model=MagicMock(),
                ss=MagicMock(),
                bus=MagicMock(),
                tool_dispatcher=MagicMock(),
                fsm_state=fsm,
            )

        mock_bch.assert_called_once()
        call_kwargs = mock_bch.call_args[1]
        assert call_kwargs["cancel_token"] is token

    def test_cancel_reason_preserved(self):
        """CancelReason is preserved through the token."""
        from poc.k1_poc.protocols.cancel_handler import CancellationHandler

        handler = CancellationHandler()
        handler.register_task("t1")
        handler.request_cancel("t1", CancelReason.TIMEOUT)

        token = handler.get_token("t1")
        assert token is not None
        assert token.cancel_reason == CancelReason.TIMEOUT

    def test_cancel_time_recorded(self):
        """Cancellation timestamp is recorded."""
        token = CancellationToken(task_id="t1")
        assert token.cancel_time_ns == 0

        token.cancel(CancelReason.USER_REQUESTED)
        assert token.cancel_time_ns > 0
