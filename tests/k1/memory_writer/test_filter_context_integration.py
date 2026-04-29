"""Integration tests for Filter + Context Assembly pipeline (E-MW-1.4).

12 tests across 3 test classes verifying the full per-turn flow:
  Filter → MWSessionReader → ContextBuilder (+ PersonResolver)
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.context_builder import ContextBuilder
from k1.memory_writer.context.person_resolver import PersonResolver
from k1.memory_writer.context.session_reader import MWSessionReader
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.filter.relevance_filter import RelevanceFilter
from k1.memory_writer.types import ExtractionContext

# ===========================================================================
# Helpers
# ===========================================================================


class FakeSessionReadPort:
    """In-memory fake for ISessionReadPort."""

    def __init__(self, snapshot_data: Optional[Dict[str, Any]] = None) -> None:
        self._data = snapshot_data or {}

    async def snapshot(self, sections: List[str]) -> Dict[str, Any]:
        return {k: v for k, v in self._data.items() if k in sections}

    async def read_section(self, name: str) -> Optional[Dict[str, Any]]:
        return self._data.get(name)

    async def list_sections(self) -> FrozenSet[str]:
        return frozenset(self._data.keys())

    async def snapshot_all(self, exclude: FrozenSet[str] = frozenset()) -> Dict[str, Any]:
        return {k: v for k, v in self._data.items() if k not in exclude}

    async def read_archived_history(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return []


def _payload(
    turn_id: str = "turn-1",
    user_message: str = "Mom called about dinner",
    turn_number: int = 1,
    **kwargs: Any,
) -> TurnCompletePayload:
    defaults = dict(
        turn_id=turn_id,
        session_id="sess-001",
        cognitive_trace_id="trace-001",
        user_message=user_message,
        assistant_response="That sounds nice!",
        timestamp_ms=1_700_000_000_000,
        turn_number=turn_number,
    )
    defaults.update(kwargs)
    return TurnCompletePayload(**defaults)


def _snapshot_with_history(*turns: Dict[str, Any], **sections: Any) -> Dict[str, Any]:
    """Build snapshot with history_active turns + optional extra sections."""
    snap: Dict[str, Any] = {
        "history_active": {"turns": list(turns)},
        "beliefs_active": sections.pop(
            "beliefs_active",
            {
                "mentioned_entities": [
                    {
                        "type": "PERSON",
                        "display_name": "Mom",
                        "person_id": "person_mom",
                        "confidence": 1.0,
                    },
                ],
            },
        ),
        "meta": sections.pop("meta", {"session_id": "sess-001"}),
    }
    snap.update(sections)
    return snap


def _turn_dict(
    turn_id: str,
    user_message: str,
    turn_number: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "turn_id": turn_id,
        "user_message": user_message,
        "timestamp_ms": 1_700_000_000_000 + turn_number * 1000,
        "turn_number": turn_number,
    }
    if metadata is not None:
        d["metadata"] = metadata
    return d


# ===========================================================================
# TestFilterDecisionFlow
# ===========================================================================


class TestFilterDecisionFlow:
    def test_trivial_turns_never_trigger_context(self):
        """5 'ok' turns all SKIP — no ContextBuilder calls."""
        config = MWConfig()
        filt = RelevanceFilter(config)
        context_builds = 0
        for i in range(5):
            decision = filt.evaluate(
                user_message="ok",
                assistant_response="Sure.",
                entities=[],
                topics=[],
                turn_id=f"t-{i}",
                timestamp_ms=1_700_000_000_000 + i * 60_000,
            )
            if decision.passed:
                context_builds += 1
        assert context_builds == 0

    def test_meaningful_turn_triggers_context(self):
        config = MWConfig()
        filt = RelevanceFilter(config)
        decision = filt.evaluate(
            user_message="Mom called about dinner plans tonight",
            assistant_response="Sounds fun!",
            entities=["Mom"],
            topics=["dinner"],
            turn_id="t-1",
            timestamp_ms=1_700_000_000_000,
        )
        assert decision.passed is True

    def test_mixed_trivial_meaningful(self):
        config = MWConfig()
        filt = RelevanceFilter(config)
        messages = [
            ("ok", [], []),
            ("Mom called about dinner plans tonight", ["Mom"], ["dinner"]),
            ("sure", [], []),
            ("She said yes to the Italian restaurant", ["She"], ["restaurant"]),
        ]
        passed_count = 0
        for i, (msg, ents, tops) in enumerate(messages):
            decision = filt.evaluate(
                user_message=msg,
                assistant_response="ok",
                entities=ents,
                topics=tops,
                turn_id=f"t-{i}",
                timestamp_ms=1_700_000_000_000 + i * 60_000,
            )
            if decision.passed:
                passed_count += 1
        assert passed_count == 2

    def test_tool_call_boost_triggers_context(self):
        config = MWConfig()
        filt = RelevanceFilter(config)
        decision = filt.evaluate(
            user_message="ok",
            assistant_response="Done.",
            entities=[],
            topics=[],
            turn_id="t-1",
            timestamp_ms=1_700_000_000_000,
            turn_metadata={"tool_calls": [{"name": "search", "status": "ok"}]},
        )
        assert decision.passed is True

    def test_dedup_prevents_double_context(self):
        config = MWConfig()
        filt = RelevanceFilter(config)
        # First turn passes
        d1 = filt.evaluate(
            user_message="Mom called about dinner",
            assistant_response="Nice!",
            entities=["Mom"],
            topics=["dinner"],
            turn_id="t-1",
            timestamp_ms=1_700_000_000_000,
        )
        assert d1.passed is True
        # Same entities+topics within 5 min → DUPLICATE
        d2 = filt.evaluate(
            user_message="Mom mentioned dinner again",
            assistant_response="Ok",
            entities=["Mom"],
            topics=["dinner"],
            turn_id="t-2",
            timestamp_ms=1_700_000_000_000 + 60_000,  # 1 min later
        )
        assert d2.passed is False


# ===========================================================================
# TestContextAssemblyFromSnapshot
# ===========================================================================


class TestContextAssemblyFromSnapshot:
    @pytest.mark.asyncio
    async def test_full_snapshot_all_sections_present(self):
        snap = _snapshot_with_history(
            _turn_dict("t-1", "Hello", 1),
            _turn_dict("t-2", "How are you?", 2),
            affective_now={"dimensions": {"valence": 0.5, "arousal": 0.3, "dominance": 0.5}},
            scoreboard={"topic_stack": [{"name": "dinner", "salience": 0.9}]},
            narrative_active={"arc_position": "RISING_ACTION"},
            control={"intents": ["log_memory"]},
            persona={"traits": ["warm"]},
            ifl={"device_id": "phone-01"},
            task_state={"active_goals": ["plan_dinner"]},
        )
        port = FakeSessionReadPort(snap)
        config = MWConfig()
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)
        payload = _payload()

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, payload)

        assert isinstance(ctx, ExtractionContext)
        assert len(ctx.recent_turns) == 2
        assert ctx.current_affect is not None
        assert ctx.active_topics == ["dinner"]
        assert "Mom" in ctx.active_persons

    @pytest.mark.asyncio
    async def test_missing_sections_partial_context(self):
        snap = {"history_active": {"turns": []}, "meta": {"session_id": "s1"}}
        port = FakeSessionReadPort(snap)
        config = MWConfig()
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, _payload())

        assert ctx.session_id == "s1"
        assert ctx.current_affect is None
        assert ctx.active_persons == {}

    @pytest.mark.asyncio
    async def test_context_includes_tool_calls(self):
        tc = [{"name": "weather_check", "status": "success"}]
        snap = _snapshot_with_history(
            _turn_dict("t-1", "check weather", 1, metadata={"tool_calls": tc}),
        )
        port = FakeSessionReadPort(snap)
        config = MWConfig()
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, _payload())

        assert 1 in ctx.tool_calls_per_turn
        assert ctx.tool_calls_per_turn[1][0]["name"] == "weather_check"

    @pytest.mark.asyncio
    async def test_context_includes_persons(self):
        snap = _snapshot_with_history(
            _turn_dict("t-1", "Mom called", 1),
        )
        port = FakeSessionReadPort(snap)
        config = MWConfig()
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, _payload())

        assert "Mom" in ctx.active_persons
        assert ctx.active_persons["Mom"]["person_id"] == "person_mom"


# ===========================================================================
# TestFullPipelinePhase1
# ===========================================================================


class TestFullPipelinePhase1:
    @pytest.mark.asyncio
    async def test_pass_turn_produces_full_context(self):
        config = MWConfig()
        filt = RelevanceFilter(config)
        payload = _payload(user_message="Mom called about dinner plans tonight")

        decision = filt.evaluate(
            user_message=payload.user_message,
            assistant_response=payload.assistant_response,
            entities=["Mom"],
            topics=["dinner"],
            turn_id=payload.turn_id,
            timestamp_ms=payload.timestamp_ms,
        )
        assert decision.passed is True

        snap = _snapshot_with_history(
            _turn_dict("t-1", "Hi there", 1),
            _turn_dict("t-2", "How is everyone?", 2),
        )
        port = FakeSessionReadPort(snap)
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, payload)

        assert isinstance(ctx, ExtractionContext)
        assert len(ctx.recent_turns) == 2
        assert (
            ctx.current_turn.user_message
            if hasattr(ctx.current_turn, "user_message")
            else ctx.current_turn.text
        )

    @pytest.mark.asyncio
    async def test_person_resolution_in_context(self):
        config = MWConfig()
        snap = _snapshot_with_history(_turn_dict("t-1", "Mom called", 1))
        port = FakeSessionReadPort(snap)
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)
        resolver = PersonResolver()

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, _payload())

        # Resolve "Mom" using PersonResolver against built context
        result = resolver.resolve("Mom", ctx)
        assert result.person_id == "person_mom"
        assert result.is_provisional is False

    @pytest.mark.asyncio
    async def test_temporal_spatial_from_payload(self):
        config = MWConfig()
        payload = _payload(
            mentioned_time_raw="yesterday evening",
            mentioned_time_resolved_ms=1_699_913_600_000,
            mentioned_time_confidence=0.9,
            mentioned_location_raw="home",
            mentioned_location_type="home",
            mentioned_location_confidence=0.95,
        )
        snap = _snapshot_with_history(_turn_dict("t-1", "We had dinner", 1))
        port = FakeSessionReadPort(snap)
        reader = MWSessionReader(port, config)
        builder = ContextBuilder(config)

        snapshot = await reader.read_snapshot()
        ctx = builder.build(snapshot, payload)

        assert ctx.mentioned_time_raw == "yesterday evening"
        assert ctx.mentioned_time_resolved_ms == 1_699_913_600_000
        assert ctx.mentioned_location_raw == "home"
