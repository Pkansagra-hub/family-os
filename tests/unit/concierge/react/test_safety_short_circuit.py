"""M13.E3 — ReAct loop SAFETY short-circuit tests.

When a tool dispatch returns a policy / safety denial (``policy_decision
== "DENY"`` or a known safety reason like ``front_capability_not_whitelisted``
or ``conscience_forbidden``), the ReAct loop must short-circuit instead
of feeding the denial back to the LLM and burning more iterations.

* Front actor → returns ``status="complete"`` with a graceful apology.
* Back actor  → returns ``status="suspended"`` with ``data["safety_denial"]``
  so the orchestrator routes the task to HIL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k1.concierge.react.loop import react_loop
from tests.k1.concierge.conftest import (
    make_hub_text_response,
    make_hub_tool_response,
)


def _patched_config() -> MagicMock:
    cfg = MagicMock()
    cfg.react.parallel_tools_enabled = False
    cfg.react.front_degenerate_fallback = "fallback"
    cfg.react.front_budget_fallback = "budget"
    cfg.llm.default_timeout_ms = 30_000
    return cfg


def _denial_result(reason: str = "front_capability_not_whitelisted") -> MagicMock:
    r = MagicMock()
    r.is_error.return_value = True
    r.is_ok.return_value = False
    r.status = "error"
    r.error = "denied"
    r.tool_name = "invoke_capability"
    r.data = {"policy_decision": "DENY", "reason": reason}
    return r


def _success_result() -> MagicMock:
    r = MagicMock()
    r.is_error.return_value = False
    r.is_ok.return_value = True
    r.status = "ok"
    r.error = None
    r.tool_name = "invoke_capability"
    r.data = {}
    return r


@pytest.mark.asyncio
async def test_front_safety_denial_short_circuits_to_apology() -> None:
    """A Front whitelist DENY on iter=0 must not trigger another LLM round."""
    resp_tools = make_hub_tool_response(
        [{"name": "invoke_capability", "arguments": {"capability_name": "x"}}]
    )
    # If the loop ever calls the LLM a second time, this would be returned.
    resp_text_after = make_hub_text_response(text="should-not-appear")

    model = AsyncMock()
    model.execute = AsyncMock(side_effect=[resp_tools, resp_text_after])

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value=_denial_result())

    with patch("k1.concierge.react.loop.get_config", return_value=_patched_config()):
        result = await react_loop(
            actor="front",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

    assert result.status == "complete"
    assert result.text and "can't help" in result.text.lower()
    # Critically: only ONE LLM call was made (no retry).
    assert model.execute.await_count == 1


@pytest.mark.asyncio
async def test_back_safety_denial_short_circuits_to_suspended() -> None:
    """Back hits a conscience_forbidden — task must suspend, not retry."""
    resp_tools = make_hub_tool_response(
        [{"name": "invoke_capability", "arguments": {"capability_name": "x"}}]
    )
    resp_text_after = make_hub_text_response(text="never-reached")

    model = AsyncMock()
    model.execute = AsyncMock(side_effect=[resp_tools, resp_text_after])

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value=_denial_result("conscience_forbidden"))

    with patch("k1.concierge.react.loop.get_config", return_value=_patched_config()):
        result = await react_loop(
            actor="back",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

    assert result.status == "suspended"
    assert result.data is not None
    assert result.data.get("safety_denial") is True
    assert result.data.get("reason") == "conscience_forbidden"
    assert model.execute.await_count == 1


@pytest.mark.asyncio
async def test_non_safety_error_does_not_short_circuit() -> None:
    """A regular tool error (no DENY / no safety reason) keeps iterating."""
    resp_tools = make_hub_tool_response([{"name": "invoke_capability", "arguments": {}}])
    resp_text = make_hub_text_response(text="recovered")

    model = AsyncMock()
    model.execute = AsyncMock(side_effect=[resp_tools, resp_text])

    err = MagicMock()
    err.is_error.return_value = True
    err.is_ok.return_value = False
    err.status = "error"
    err.error = "transient"
    err.tool_name = "invoke_capability"
    err.data = {"reason": "network_timeout"}  # NOT a safety reason

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value=err)

    with patch("k1.concierge.react.loop.get_config", return_value=_patched_config()):
        result = await react_loop(
            actor="front",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

    # Loop continued — at least 2 LLM calls happened.
    assert model.execute.await_count >= 2
    assert result.status == "complete"


@pytest.mark.asyncio
async def test_safety_short_circuit_records_iteration_duration() -> None:
    """Iteration duration must be recorded even on the short-circuit path."""
    resp_tools = make_hub_tool_response([{"name": "invoke_capability", "arguments": {}}])

    model = AsyncMock()
    model.execute = AsyncMock(return_value=resp_tools)

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value=_denial_result("policy_deny"))

    with patch("k1.concierge.react.loop.get_config", return_value=_patched_config()):
        result = await react_loop(
            actor="front",
            system_prompt="test",
            messages=[],
            tools=[MagicMock()],
            max_iterations=5,
            model=model,
            tool_dispatcher=dispatcher,
            on_text_response=AsyncMock(),
            cancellation_check=AsyncMock(return_value=False),
        )

    assert result.status == "complete"
    assert len(result.iteration_durations_ms) == 1
