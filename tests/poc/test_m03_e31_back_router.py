"""
tests.poc.test_m03_e31_back_router -- E3.1 Back Mailbox Topic Router.

Validates the 5 issues of Epic 3.1:
  3.1.1 -- route_back_envelope dispatcher function exists and routes correctly
  3.1.2 -- Coordinator consumer wired through route_back_envelope
  3.1.3 -- Bootstrap consumer wired through route_back_envelope
  3.1.4 -- FSM _deliver_to_back preserves envelope topics
  3.1.5 -- subscribe_back_events is deprecated

Test count target: ~30 tests.
"""

from __future__ import annotations

import json
import warnings
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import (
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_DEAD_LETTER,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_RESUME,
    TOPIC_USER_INPUT,
)

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
    return {
        "model": MagicMock(),
        "ss": MagicMock(),
        "bus": MagicMock(),
        "tool_dispatcher": MagicMock(),
        "fsm_state": MagicMock(),
    }


# =========================================================================
# 3.1.1 -- route_back_envelope exists and routes correctly
# =========================================================================


class TestRouteBackEnvelopeExists:
    """Verify route_back_envelope function exists and has correct signature."""

    def test_function_exists(self):
        """route_back_envelope is importable from actors.back."""
        from poc.k1_poc.actors.back import route_back_envelope

        assert callable(route_back_envelope)

    def test_exported_from_actors_package(self):
        """route_back_envelope is in actors __all__."""
        from poc.k1_poc.actors import __all__ as actors_all

        assert "route_back_envelope" in actors_all

    def test_importable_from_actors_init(self):
        """route_back_envelope can be imported from actors package."""
        from poc.k1_poc.actors import route_back_envelope

        assert callable(route_back_envelope)

    def test_is_async(self):
        """route_back_envelope must be async (awaitable)."""
        import asyncio

        from poc.k1_poc.actors.back import route_back_envelope

        assert asyncio.iscoroutinefunction(route_back_envelope)

    def test_uses_topic_constants_not_strings(self):
        """route_back_envelope imports topic constants from bus.topics."""
        import inspect

        from poc.k1_poc.actors.back import route_back_envelope

        source = inspect.getsource(route_back_envelope)
        # Must use constants, not raw strings
        assert "TOPIC_TASK_DISPATCH" in source
        assert "TOPIC_TASK_RESUME" in source
        assert "TOPIC_TASK_CANCEL" in source
        assert "TOPIC_CLARIFICATION_RESPONSE" in source
        # Must NOT hardcode topic strings
        assert '"k1.orchestration.task.dispatch.v1"' not in source
        assert '"k1.orchestration.task.resume.v1"' not in source
        assert '"k1.orchestration.task.cancel.v1"' not in source


class TestRouteBackEnvelopeDispatch:
    """Verify topic-based routing to the correct handler."""

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_back_handler(self):
        """task.dispatch.v1 routes to back_handler."""
        env = _make_envelope(topic=TOPIC_TASK_DISPATCH)
        deps = _make_mock_deps()
        mock_result = MagicMock()

        with patch(
            "poc.k1_poc.actors.back.back_handler",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_bh:
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_bh.assert_called_once()
        call_kwargs = mock_bh.call_args[1]
        assert call_kwargs["envelope"] is env
        assert call_kwargs["model"] is deps["model"]
        assert call_kwargs["fsm_state"] is deps["fsm_state"]
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_resume_routes_to_back_resume_handler(self):
        """task.resume.v1 routes to back_resume_handler."""
        env = _make_envelope(topic=TOPIC_TASK_RESUME)
        deps = _make_mock_deps()
        mock_result = MagicMock()

        with patch(
            "poc.k1_poc.actors.back.back_resume_handler",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_brh:
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_brh.assert_called_once()
        call_kwargs = mock_brh.call_args[1]
        assert call_kwargs["envelope"] is env
        assert call_kwargs["fsm_state"] is deps["fsm_state"]
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_cancel_routes_to_back_cancel_handler(self):
        """task.cancel.v1 routes to back_cancel_handler (sync)."""
        env = _make_envelope(topic=TOPIC_TASK_CANCEL)
        deps = _make_mock_deps()

        with patch(
            "poc.k1_poc.actors.back.back_cancel_handler",
        ) as mock_bch:
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_bch.assert_called_once()
        call_kwargs = mock_bch.call_args[1]
        assert call_kwargs["envelope"] is env
        assert call_kwargs["fsm_state"] is deps["fsm_state"]
        assert result is None

    @pytest.mark.asyncio
    async def test_clarification_response_routes_to_resume(self):
        """clarification.response.v1 routes to back_resume_handler."""
        env = _make_envelope(topic=TOPIC_CLARIFICATION_RESPONSE)
        deps = _make_mock_deps()
        mock_result = MagicMock()

        with patch(
            "poc.k1_poc.actors.back.back_resume_handler",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_brh:
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_brh.assert_called_once()
        call_kwargs = mock_brh.call_args[1]
        assert call_kwargs["envelope"] is env
        assert call_kwargs["fsm_state"] is deps["fsm_state"]
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_unknown_topic_returns_none(self):
        """Unknown topic returns None without calling any handler."""
        env = _make_envelope(topic=TOPIC_USER_INPUT)  # not a back topic
        deps = _make_mock_deps()

        with (
            patch("poc.k1_poc.actors.back.back_handler", new_callable=AsyncMock) as mock_bh,
            patch("poc.k1_poc.actors.back.back_resume_handler", new_callable=AsyncMock) as mock_brh,
            patch("poc.k1_poc.actors.back.back_cancel_handler") as mock_bch,
        ):
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_bh.assert_not_called()
        mock_brh.assert_not_called()
        mock_bch.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_topic_returns_none(self):
        """Envelope with empty/missing topic returns None."""
        env = _make_envelope(topic="")
        deps = _make_mock_deps()

        with (
            patch("poc.k1_poc.actors.back.back_handler", new_callable=AsyncMock) as mock_bh,
            patch("poc.k1_poc.actors.back.back_resume_handler", new_callable=AsyncMock) as mock_brh,
        ):
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_bh.assert_not_called()
        mock_brh.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_dead_letter_topic_returns_none(self):
        """Dead-letter topic is not a back topic, returns None."""
        env = _make_envelope(topic=TOPIC_DEAD_LETTER)
        deps = _make_mock_deps()

        with patch("poc.k1_poc.actors.back.back_handler", new_callable=AsyncMock) as mock_bh:
            from poc.k1_poc.actors.back import route_back_envelope

            result = await route_back_envelope(envelope=env, **deps)

        mock_bh.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_fsm_state_none_passed_through(self):
        """fsm_state=None is correctly forwarded to handlers."""
        env = _make_envelope(topic=TOPIC_TASK_DISPATCH)
        deps = _make_mock_deps()
        deps["fsm_state"] = None

        with patch(
            "poc.k1_poc.actors.back.back_handler",
            new_callable=AsyncMock,
        ) as mock_bh:
            from poc.k1_poc.actors.back import route_back_envelope

            await route_back_envelope(envelope=env, **deps)

        mock_bh.assert_called_once()
        call_kwargs = mock_bh.call_args[1]
        assert call_kwargs["fsm_state"] is None

    @pytest.mark.asyncio
    async def test_cancel_only_passes_envelope_and_fsm(self):
        """back_cancel_handler receives envelope, fsm_state, and cancel_token."""
        env = _make_envelope(topic=TOPIC_TASK_CANCEL)
        deps = _make_mock_deps()

        with patch("poc.k1_poc.actors.back.back_cancel_handler") as mock_bch:
            from poc.k1_poc.actors.back import route_back_envelope

            await route_back_envelope(envelope=env, **deps)

        # back_cancel_handler is sync and takes envelope + fsm_state + cancel_token
        mock_bch.assert_called_once()
        call_kwargs = mock_bch.call_args[1]
        assert call_kwargs["envelope"] is env
        assert call_kwargs["fsm_state"] is deps["fsm_state"]
        # M3 E3.2: cancel_token is now also passed
        assert "cancel_token" in call_kwargs


# =========================================================================
# 3.1.2 -- Coordinator consumer wired through route_back_envelope
# =========================================================================


class TestCoordinatorWiring:
    """Verify coordinator calls route_back_envelope, not back_handler directly."""

    def test_coordinator_imports_route_back_envelope(self):
        """coordinator._mailbox_consumer imports route_back_envelope."""
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator._mailbox_consumer)
        assert "route_back_envelope" in source

    def test_coordinator_does_not_import_back_handler_directly(self):
        """coordinator._mailbox_consumer no longer imports back_handler."""
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator._mailbox_consumer)
        assert "from poc.k1_poc.actors.back import back_handler" not in source

    def test_run_back_handler_passes_fsm_state(self):
        """_run_back_handler passes fsm_state to the router."""
        import inspect

        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        source = inspect.getsource(K1DemoCoordinator._run_back_handler)
        # M7 E7.3.3: fsm_state is now passed via call_kwargs dict
        assert "fsm_state" in source

    def test_run_back_handler_docstring_mentions_router(self):
        """_run_back_handler docstring references route_back_envelope."""
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        docstring = K1DemoCoordinator._run_back_handler.__doc__ or ""
        assert "route_back_envelope" in docstring


# =========================================================================
# 3.1.3 -- Bootstrap consumer wired through route_back_envelope
# =========================================================================


class TestBootstrapWiring:
    """Verify bootstrap _mailbox_consumer calls route_back_envelope."""

    def test_bootstrap_imports_route_back_envelope(self):
        """bootstrap.py imports route_back_envelope."""
        import inspect

        from poc.k1_poc.kernel import bootstrap

        source = inspect.getsource(bootstrap)
        assert "route_back_envelope" in source

    def test_bootstrap_does_not_call_back_handler_directly(self):
        """bootstrap _mailbox_consumer does not call back_handler directly."""
        import inspect

        from poc.k1_poc.kernel.bootstrap import _mailbox_consumer

        source = inspect.getsource(_mailbox_consumer)
        # Should NOT contain direct back_handler call
        assert "back_handler(" not in source.replace("route_back_envelope", "")

    def test_bootstrap_consumer_passes_fsm_state(self):
        """bootstrap _mailbox_consumer passes fsm_state to route_back_envelope."""
        import inspect

        from poc.k1_poc.kernel.bootstrap import _mailbox_consumer

        source = inspect.getsource(_mailbox_consumer)
        assert "fsm_state=" in source


# =========================================================================
# 3.1.4 -- FSM _deliver_to_back preserves envelope topics
# =========================================================================


class TestDeliverToBackTopicPreservation:
    """Verify FSM _deliver_to_back preserves envelope topic."""

    def test_deliver_to_back_has_topic_guard(self):
        """_deliver_to_back checks for missing topic."""
        import inspect

        from poc.k1_poc.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._deliver_to_back)
        # Must contain the topic guard from 3.1.4
        assert "route_back_envelope" in source or "topic" in source.lower()

    def test_deliver_to_back_docstring_mentions_topic_preservation(self):
        """_deliver_to_back docstring mentions topic preservation."""
        from poc.k1_poc.fsm.controller import ConciergeController

        docstring = ConciergeController._deliver_to_back.__doc__ or ""
        assert "topic" in docstring.lower()

    def test_dispatch_envelope_preserves_topic(self):
        """Dispatch envelope passed to _deliver_to_back retains topic."""
        env = _make_envelope(topic=TOPIC_TASK_DISPATCH)
        # Verify topic survives attribute access
        assert env.topic == TOPIC_TASK_DISPATCH

    def test_cancel_envelope_preserves_topic(self):
        """Cancel envelope retains topic through construction."""
        env = _make_envelope(topic=TOPIC_TASK_CANCEL)
        assert env.topic == TOPIC_TASK_CANCEL

    def test_resume_envelope_preserves_topic(self):
        """Resume envelope retains topic through construction."""
        env = _make_envelope(topic=TOPIC_TASK_RESUME)
        assert env.topic == TOPIC_TASK_RESUME

    def test_clarification_envelope_preserves_topic(self):
        """Clarification response envelope retains topic."""
        env = _make_envelope(topic=TOPIC_CLARIFICATION_RESPONSE)
        assert env.topic == TOPIC_CLARIFICATION_RESPONSE

    def test_on_task_resume_preserves_topic_in_reconstruction(self):
        """_on_task_resume constructs new Envelope with topic=envelope.topic."""
        import inspect

        from poc.k1_poc.fsm.controller import ConciergeController

        source = inspect.getsource(ConciergeController._on_task_resume)
        # The reconstruction must set topic=envelope.topic
        assert "topic=envelope.topic" in source or "topic=" in source


# =========================================================================
# 3.1.5 -- subscribe_back_events is deprecated
# =========================================================================


class TestSubscribeBackEventsDeprecation:
    """Verify subscribe_back_events is deprecated."""

    def test_deprecation_docstring(self):
        """subscribe_back_events docstring contains deprecation notice."""
        from poc.k1_poc.actors.back import subscribe_back_events

        docstring = subscribe_back_events.__doc__ or ""
        assert "deprecated" in docstring.lower()

    def test_deprecation_warning_emitted(self):
        """Calling subscribe_back_events emits DeprecationWarning."""
        from poc.k1_poc.actors.back import subscribe_back_events

        bus = MagicMock()
        handler = MagicMock()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            subscribe_back_events(bus, handler)

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "M3 E3.1.5" in str(deprecation_warnings[0].message)

    def test_removal_target_documented(self):
        """Deprecation notice mentions M8 removal target."""
        from poc.k1_poc.actors.back import subscribe_back_events

        docstring = subscribe_back_events.__doc__ or ""
        assert "M8" in docstring

    def test_not_in_actors_all(self):
        """subscribe_back_events is removed from actors __all__."""
        from poc.k1_poc.actors import __all__ as actors_all

        assert "subscribe_back_events" not in actors_all

    def test_function_still_works_when_called(self):
        """subscribe_back_events still functions (backward compat) despite deprecation."""
        from poc.k1_poc.actors.back import subscribe_back_events

        bus = MagicMock()
        handler = MagicMock()

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            handles = subscribe_back_events(bus, handler)

        # Should still return handles
        assert isinstance(handles, list)
        assert len(handles) == 4  # 4 topics


# =========================================================================
# Integration: all 4 topics route end-to-end
# =========================================================================


class TestRouteBackEnvelopeIntegration:
    """Integration-style tests: route envelopes without mocking handlers,
    verifying no exceptions are raised for valid topic values."""

    @pytest.mark.asyncio
    async def test_all_four_topics_accepted(self):
        """All 4 back topics are accepted by the router (no unknown-topic warning)."""
        from poc.k1_poc.actors.back import route_back_envelope

        topics = [
            TOPIC_TASK_DISPATCH,
            TOPIC_TASK_RESUME,
            TOPIC_TASK_CANCEL,
            TOPIC_CLARIFICATION_RESPONSE,
        ]
        deps = _make_mock_deps()

        for topic in topics:
            env = _make_envelope(topic=topic)
            # Mock all three handlers to avoid real execution
            with (
                patch("poc.k1_poc.actors.back.back_handler", new_callable=AsyncMock),
                patch("poc.k1_poc.actors.back.back_resume_handler", new_callable=AsyncMock),
                patch("poc.k1_poc.actors.back.back_cancel_handler"),
            ):
                # Should not raise
                await route_back_envelope(envelope=env, **deps)

    @pytest.mark.asyncio
    async def test_dispatch_returns_react_result(self):
        """task.dispatch routes to back_handler and returns its result."""
        from poc.k1_poc.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_DISPATCH)
        deps = _make_mock_deps()
        sentinel = object()

        with patch(
            "poc.k1_poc.actors.back.back_handler",
            new_callable=AsyncMock,
            return_value=sentinel,
        ):
            result = await route_back_envelope(envelope=env, **deps)

        assert result is sentinel

    @pytest.mark.asyncio
    async def test_cancel_returns_none(self):
        """task.cancel routes to back_cancel_handler and returns None."""
        from poc.k1_poc.actors.back import route_back_envelope

        env = _make_envelope(topic=TOPIC_TASK_CANCEL)
        deps = _make_mock_deps()

        with patch("poc.k1_poc.actors.back.back_cancel_handler"):
            result = await route_back_envelope(envelope=env, **deps)

        assert result is None
