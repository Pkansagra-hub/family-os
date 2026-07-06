"""Epic 15.7 — Verify temporal/spatial/selfmodel context blocks reach Back's prompt.

Tests at two levels:
1.  Unit: ``build_back_prompt()`` with populated blocks — verify placeholder resolution
2.  Integration: ``back_handler()`` with mock handles — verify handle→block→prompt chain

All tests are single-process.  Run:
    pytest tests/k1/concierge/actors/test_back_context_wiring.py -v -p no:xdist -p no:cacheprovider
"""

from __future__ import annotations

import pytest

import k1.concierge.actors.back as back_mod
from k1.concierge.bus.builders import build_task_dispatch
from k1.concierge.bus.setup import create_poc_bus
from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
from k1.concierge.llm.types import (
    ConciergeModelResponse,
    FinishReason,
    ToolCallResult,
)
from k1.concierge.prompt.back_prompt import build_back_prompt
from k1.concierge.tools.dispatcher import create_back_dispatcher
from k1.concierge.tools.implementations import ToolContext
from k1.sessionstate.factory import SessionStateFactory

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_dispatcher(bus, session_state):
    ctx = ToolContext(session_manager=session_state, actor="back")
    return create_back_dispatcher(tier="simple", ctx=ctx, bus=bus)


def _model_for_recall_then_submit() -> TestModelHubBridge:
    model = TestModelHubBridge()
    model.set_response_sequence(
        "back",
        "",
        [
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-recall",
                        name="recall_memory",
                        arguments={"query": "test", "memory_types": ["semantic"], "max_results": 1},
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-submit",
                        name="submit_result",
                        arguments={
                            "result_type": "complete",
                            "final_answer": "done",
                            "results": [],
                            "artifacts_created": [],
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
        ],
    )
    return model


async def _run_back_handler_and_get_prompt(**kwargs) -> str:
    """Run back_handler with given kwargs, return the system prompt."""
    bus = create_poc_bus(capture=True)
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()
    model = _model_for_recall_then_submit()
    envelope = build_task_dispatch(
        {
            "task_id": "ctx-wire-1",
            "tier": "LOW",
            "intents": [{"action": "schedule dentist", "domain": "calendar"}],
        }
    )

    handler_kwargs = {
        "envelope": envelope,
        "model": model,
        "ss": session_state,
        "bus": bus,
        "tool_dispatcher": _make_dispatcher(bus, session_state),
    }
    handler_kwargs.update(kwargs)

    try:
        await back_mod.back_handler(**handler_kwargs)
    finally:
        session_state.stop()

    request = model.inner.calls_for("back", "")[0]
    return request.system_prompt


# ── Mock handles ─────────────────────────────────────────────────────────


class _MockTemporalHandle:
    """Returns a TemporalProjection-like object for the prose renderer."""

    async def get_projection(self, consumer: str = "back"):
        class _MockAnchor:
            anchor_id = "t-mock-1"
            now_utc = "2026-06-09T17:00:00Z"
            now_local = "2026-06-09T12:00:00-05:00"
            timezone = "America/Chicago"
            timezone_source = "device"
            local_date = "2026-06-09"
            day_of_week = "Tuesday"
            time_of_day = "afternoon"

        class _MockProjection:
            anchor = _MockAnchor()
            freshness = "fresh"
            windows: dict = {}
            resolved_expressions: list = []

        return _MockProjection()


class _MockSpatialHandle:
    """Returns a predictable spatial projection."""

    async def get_projection(self, consumer: str = "back"):
        class _MockProjection:
            device_location = "home (lat=41.88, lon=-87.63)"
            home_location = "Chicago, IL - 123 Main St"

        return _MockProjection()


class _MockSelfModelHandle:
    """Returns a predictable selfmodel capsule."""

    def render_capsule(self):
        class _MockCapsule:
            def as_prompt_text(self):
                return "== SELFMODEL ==\nuser_preference: morning_appointments\nuser_dietary: vegan"

        return _MockCapsule()


class _MockGroundingHandle:
    """Returns None — forces the raw-fields fallback in _build_execution_grounding_block.

    The real render_execution_grounding_block requires a full GroundingProjection
    with deeply nested temporal/spatial/freshness sub-objects.  Rather than mock
    that entire tree, we test the grounding path via the raw task fields fallback
    (which is the production path for tasks that carry grounding_envelope_id +
    temporal_anchor_id in their dispatch payload).
    """

    async def get_projection(self, consumer: str = "back") -> None:
        return None


# ── Unit tests: build_back_prompt ────────────────────────────────────────


class TestBackPromptPlaceholderResolution:
    """build_back_prompt() correctly substitutes all context narratives."""

    def test_temporal_narrative_appears_in_prompt(self):
        prompt = build_back_prompt(
            task={"task_id": "t1", "intents": [{"action": "test"}], "tier": "LOW"},
            temporal_context_block="It is Tuesday night, June 9, 2026 in America/Chicago.",
        )
        assert "It is Tuesday night, June 9, 2026" in prompt

    def test_spatial_narrative_appears_in_prompt(self):
        prompt = build_back_prompt(
            task={"task_id": "t1", "intents": [{"action": "test"}], "tier": "LOW"},
            spatial_context_block="The user is currently at home in Chicago.",
        )
        assert "currently at home in Chicago" in prompt

    def test_selfmodel_narrative_appears_in_prompt(self):
        prompt = build_back_prompt(
            task={"task_id": "t1", "intents": [{"action": "test"}], "tier": "LOW"},
            selfmodel_context_block="You are acting on behalf of Alex, who prefers mornings.",
        )
        assert "acting on behalf of Alex" in prompt

    def test_all_three_narratives_appear_together(self):
        prompt = build_back_prompt(
            task={"task_id": "t1", "intents": [{"action": "test"}], "tier": "LOW"},
            temporal_context_block="TEMPORAL-MARKER-T1",
            spatial_context_block="SPATIAL-MARKER-S1",
            selfmodel_context_block="SELFMODEL-MARKER-M1",
        )
        assert "TEMPORAL-MARKER-T1" in prompt
        assert "SPATIAL-MARKER-S1" in prompt
        assert "SELFMODEL-MARKER-M1" in prompt
        # Ordering: temporal before spatial before selfmodel
        assert prompt.index("TEMPORAL-MARKER-T1") < prompt.index("SPATIAL-MARKER-S1")
        assert prompt.index("SPATIAL-MARKER-S1") < prompt.index("SELFMODEL-MARKER-M1")

    def test_empty_blocks_render_explicit_defaults(self):
        prompt = build_back_prompt(
            task={"task_id": "t1", "intents": [{"action": "test"}], "tier": "LOW"},
        )
        for placeholder in [
            "{temporal_narrative}",
            "{spatial_narrative}",
            "{selfmodel_narrative}",
        ]:
            assert placeholder not in prompt, f"Leaked: {placeholder}"
        # Empty blocks now render explicit absence statements, not blanks.
        assert "current date and time were not resolved" in prompt
        assert "location is unknown" in prompt
        assert "No user profile is attached" in prompt

    def test_backward_compat_no_new_params(self):
        """Calling with only the old params must not raise KeyError."""
        prompt = build_back_prompt(
            task={"task_id": "t1", "intents": [{"action": "test"}], "tier": "LOW"},
            beliefs="test belief",
            task_state="2 active",
        )
        assert "test belief" in prompt
        assert "2 active" in prompt


# ── Integration tests: back_handler with mock handles ────────────────────


class TestTemporalContextReachesBackPrompt:
    """TemporalHandle output appears in the system prompt via back_handler."""

    @pytest.mark.asyncio
    async def test_temporal_narrative_in_prompt(self):
        temporal = _MockTemporalHandle()
        prompt = await _run_back_handler_and_get_prompt(temporal=temporal)
        # Prose narrative built from the mock projection
        assert "It is Tuesday" in prompt
        assert "America/Chicago" in prompt


class TestSpatialContextReachesBackPrompt:
    """SpatialHandle output appears in the system prompt via back_handler."""

    @pytest.mark.asyncio
    async def test_spatial_narrative_in_prompt(self):
        spatial = _MockSpatialHandle()
        prompt = await _run_back_handler_and_get_prompt(spatial=spatial)
        assert "Chicago" in prompt
        assert "123 Main St" in prompt


class TestSelfModelContextReachesBackPrompt:
    """SelfModelHandle output appears in the system prompt via back_handler."""

    @pytest.mark.asyncio
    async def test_selfmodel_block_in_prompt(self):
        self_model = _MockSelfModelHandle()
        prompt = await _run_back_handler_and_get_prompt(self_model=self_model)
        assert "user_preference: morning_appointments" in prompt
        assert "user_dietary: vegan" in prompt


class TestAllContextsReachBackPrompt:
    """All 3 handles + grounding produce narratives in the same prompt."""

    @pytest.mark.asyncio
    async def test_all_four_contexts_in_prompt(self):
        temporal = _MockTemporalHandle()
        spatial = _MockSpatialHandle()
        self_model = _MockSelfModelHandle()
        grounding = _MockGroundingHandle()

        prompt = await _run_back_handler_and_get_prompt(
            temporal=temporal,
            spatial=spatial,
            self_model=self_model,
            grounding=grounding,
        )

        assert "It is Tuesday" in prompt
        assert "123 Main St" in prompt
        assert "user_dietary: vegan" in prompt

        # Ordering: temporal → spatial → selfmodel → (grounding/profiles) → ss data
        assert prompt.index("It is Tuesday") < prompt.index("123 Main St")
        assert prompt.index("123 Main St") < prompt.index("user_dietary")


class TestHandlesNoneStillWorks:
    """When all handles are None, back_handler must not crash and prompt must build."""

    @pytest.mark.asyncio
    async def test_handles_none_ok(self):
        prompt = await _run_back_handler_and_get_prompt(
            temporal=None,
            spatial=None,
            self_model=None,
            grounding=None,
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "== IDENTITY ==" in prompt
        assert "== SITUATIONAL CONTEXT ==" in prompt
        assert "== SESSION STATE ==" in prompt


class TestGroundingStillReachesBackPrompt:
    """Regression: existing grounding block still works through back_handler."""

    @pytest.mark.asyncio
    async def test_grounding_block_from_task_payload(self):
        # Use raw grounding fields (fallback path) rather than dict_to_projection
        # which requires a full GroundingProjection shape.
        envelope = build_task_dispatch(
            {
                "task_id": "grounding-test-1",
                "tier": "LOW",
                "intents": [{"action": "schedule dentist", "domain": "calendar"}],
                "grounding_envelope_id": "g-task-001",
                "temporal_anchor_id": "ta-1",
            }
        )

        bus = create_poc_bus(capture=True)
        session_state = SessionStateFactory.create_for_testing()
        session_state.start()
        model = _model_for_recall_then_submit()

        try:
            await back_mod.back_handler(
                envelope=envelope,
                model=model,
                ss=session_state,
                bus=bus,
                tool_dispatcher=_make_dispatcher(bus, session_state),
            )
        finally:
            session_state.stop()

        request = model.inner.calls_for("back", "")[0]
        prompt = request.system_prompt
        # Grounding now renders as provenance prose, not a raw block.
        assert "grounding envelope g-task-001" in prompt
        assert "temporal anchor ta-1" in prompt
