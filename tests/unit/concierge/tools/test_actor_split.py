"""M13.E1.I5 -- Front actor split tests.

Verifies that the Front voice cannot directly invoke side-effecting
or safety-sensitive capabilities; only members of
``FRONT_READ_CAPABILITY_WHITELIST`` are permitted.

Surfaces tested:
  1. ``FRONT_READ_CAPABILITY_WHITELIST`` shape.
  2. ``ConciergePolicyGate`` with ``actor_role="front"`` DENIES
     ``invoke_capability(capability_name=<not in whitelist>)`` BEFORE
     the policy evaluator runs.
  3. ``ConciergePolicyGate`` with ``actor_role="front"`` ALLOWS
     ``invoke_capability(capability_name=<in whitelist>)``.
  4. ``ConciergePolicyGate`` with ``actor_role="back"`` ignores the
     whitelist (Back may invoke anything subject to policy).
  5. ``execute_invoke_capability`` defense-in-depth: when called with
     ``ctx.actor == "front"`` and a non-whitelisted capability, returns
     an error envelope without dispatching.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from k1.concierge.llm.types import ToolCallResult
from k1.concierge.tools.implementations import execute_invoke_capability
from k1.concierge.tools.schemas_front import FRONT_READ_CAPABILITY_WHITELIST

# ---------------------------------------------------------------------------
# 1. Whitelist shape
# ---------------------------------------------------------------------------


def test_whitelist_is_frozenset_of_str() -> None:
    assert isinstance(FRONT_READ_CAPABILITY_WHITELIST, frozenset)
    assert all(isinstance(x, str) for x in FRONT_READ_CAPABILITY_WHITELIST)
    assert len(FRONT_READ_CAPABILITY_WHITELIST) > 0


def test_whitelist_excludes_storyline_safety_acts() -> None:
    # None of the storyline / RED / safety_sensitive acts may be in the
    # Front whitelist. They MUST go through Back via dispatch_task.
    forbidden = {
        "tool.execute.prescribe_medication",
        "tool.execute.share_location",
        "tool.execute.set_routine",
        "tool.execute.wellness_call",
        "tool.execute.grocery_order",
        "tool.execute.send_message",
        "tool.execute.calendar_create_event",
        "tool.execute.calendar_delete_event",
        "tool.execute.notes_create",
        "tool.execute.recipe_meal_plan",
        "tool.execute.build_agent",
    }
    assert FRONT_READ_CAPABILITY_WHITELIST.isdisjoint(forbidden), (
        f"Whitelist must not contain side-effecting acts: "
        f"{FRONT_READ_CAPABILITY_WHITELIST & forbidden}"
    )


# ---------------------------------------------------------------------------
# 2-4. ConciergePolicyGate enforcement
# ---------------------------------------------------------------------------


def _build_gate(actor_role: str = "front") -> Any:
    from k1.selfmodel.adapters.concierge_policy_gate import ConciergePolicyGate
    from k1.selfmodel.contracts.situation import SituationFrame

    frame = SituationFrame(
        actor_id="member.alice",
        situation_kind="S1",
        composed_at_ms=1_700_000_000_000,
        device_id="dev-1",
    )

    def _provider(_call: Any) -> SituationFrame:
        return frame

    return ConciergePolicyGate(
        actor_id="member.alice",
        frame_provider=_provider,
        actor_role=actor_role,
    )


@pytest.mark.asyncio
async def test_front_invoke_non_whitelisted_capability_is_denied() -> None:
    gate = _build_gate(actor_role="front")
    call = ToolCallResult(
        id="c1",
        name="invoke_capability",
        arguments={
            "capability_name": "tool.execute.prescribe_medication",
            "params": {},
        },
    )
    result = await gate.evaluate(call)
    assert result is not None
    assert result.is_error()
    assert "Front" in (result.error or "")
    assert result.data.get("policy_decision") == "DENY"
    assert result.data.get("reason") == "front_capability_not_whitelisted"


@pytest.mark.asyncio
async def test_front_invoke_whitelisted_capability_passes_through_gate() -> None:
    gate = _build_gate(actor_role="front")
    whitelisted = next(iter(FRONT_READ_CAPABILITY_WHITELIST))
    call = ToolCallResult(
        id="c2",
        name="invoke_capability",
        arguments={"capability_name": whitelisted, "params": {}},
    )
    # The gate may still evaluate the policy matrix and return a
    # decision, but it must NOT short-circuit with our DENY message.
    result = await gate.evaluate(call)
    if result is not None and result.is_error():
        assert result.data.get("reason") != "front_capability_not_whitelisted"


@pytest.mark.asyncio
async def test_back_invoke_non_whitelisted_capability_skips_whitelist() -> None:
    gate = _build_gate(actor_role="back")
    call = ToolCallResult(
        id="c3",
        name="invoke_capability",
        arguments={
            "capability_name": "tool.execute.prescribe_medication",
            "params": {},
        },
    )
    result = await gate.evaluate(call)
    # Back must not be hit by the Front-only whitelist DENY. Either
    # passes (None) or is denied for unrelated policy reasons.
    if result is not None:
        assert result.data.get("reason") != "front_capability_not_whitelisted"


@pytest.mark.asyncio
async def test_legacy_no_actor_role_skips_whitelist() -> None:
    """Default actor_role='' preserves legacy behavior (no whitelist)."""
    gate = _build_gate(actor_role="")
    call = ToolCallResult(
        id="c4",
        name="invoke_capability",
        arguments={
            "capability_name": "tool.execute.prescribe_medication",
            "params": {},
        },
    )
    result = await gate.evaluate(call)
    if result is not None:
        assert result.data.get("reason") != "front_capability_not_whitelisted"


# ---------------------------------------------------------------------------
# 5. Dispatcher handler defense-in-depth
# ---------------------------------------------------------------------------


def _make_ctx(actor: str) -> Any:
    """Minimal ToolContext stub: dispatch=None forces stub-mode.

    M17.E1.I1: ``allow_dispatch_passthrough=True`` keeps the legacy POC
    fallback so the back-handler permissive test below still observes
    a success path. The hard-fail behaviour is covered separately in
    ``test_dispatch_passthrough_gate.py``.
    """
    return SimpleNamespace(
        actor=actor,
        dispatch=None,
        session_id="test-session",
        active_task_id=None,
        capability_cache={},
        cognitive_trace_id="trace-1",
        allow_dispatch_passthrough=True,
        # The remaining attributes are unused by execute_invoke_capability
        # along the front-deny path.
    )


@pytest.mark.asyncio
async def test_front_handler_rejects_non_whitelisted_without_dispatch() -> None:
    ctx = _make_ctx("front")
    result = await execute_invoke_capability(
        {
            "capability_name": "tool.execute.prescribe_medication",
            "params": {},
        },
        ctx,
    )
    assert result.is_error()
    assert "Front" in (result.error or "")


@pytest.mark.asyncio
async def test_back_handler_allows_non_whitelisted_capability() -> None:
    ctx = _make_ctx("back")
    result = await execute_invoke_capability(
        {
            "capability_name": "tool.execute.prescribe_medication",
            "params": {},
        },
        ctx,
    )
    # Back path: dispatch=None falls through to POC stub success.
    assert result.is_ok()
