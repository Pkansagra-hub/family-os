"""Tests for MWSessionReader + ContextBuilder (E-MW-1.2).

26 tests across 6 test classes covering session read,
history extraction, tool calls, affect, topics, and integrated build.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.context_builder import ContextBuilder
from k1.memory_writer.context.session_reader import MWSessionReader
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.invariants import InvariantViolation
from k1.memory_writer.types import Affect, ExtractionContext

# ===========================================================================
# Helpers
# ===========================================================================


class FakeSessionReadPort:
    """In-memory fake for ISessionReadPort."""

    def __init__(
        self,
        snapshot_data: Optional[Dict[str, Any]] = None,
        latency_ns: int = 0,
    ) -> None:
        self._data = snapshot_data or {}
        self._latency_ns = latency_ns
        self.last_exclude: Optional[FrozenSet[str]] = None

    async def snapshot(self, sections: List[str]) -> Dict[str, Any]:
        return {k: v for k, v in self._data.items() if k in sections}

    async def read_section(self, name: str) -> Optional[Dict[str, Any]]:
        return self._data.get(name)

    async def list_sections(self) -> FrozenSet[str]:
        return frozenset(self._data.keys())

    async def snapshot_all(self, exclude: FrozenSet[str] = frozenset()) -> Dict[str, Any]:
        self.last_exclude = exclude
        if self._latency_ns > 0:
            # Busy-wait to simulate latency
            import time

            end = time.perf_counter_ns() + self._latency_ns
            while time.perf_counter_ns() < end:
                pass
        return {k: v for k, v in self._data.items() if k not in exclude}

    async def read_archived_history(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return []


def _make_payload(**overrides: Any) -> TurnCompletePayload:
    defaults = dict(
        turn_id="turn-99",
        session_id="sess-001",
        cognitive_trace_id="trace-001",
        user_message="Mom called about dinner",
        assistant_response="That sounds nice!",
        timestamp_ms=1_700_000_000_000,
        turn_number=5,
    )
    defaults.update(overrides)
    return TurnCompletePayload(**defaults)


def _make_turn_dict(
    turn_id: str = "turn-1",
    user_message: str = "Hello",
    timestamp_ms: int = 1_700_000_000_000,
    turn_number: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
    sub_entries: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "turn_id": turn_id,
        "user_message": user_message,
        "timestamp_ms": timestamp_ms,
        "turn_number": turn_number,
    }
    if metadata is not None:
        d["metadata"] = metadata
    if sub_entries is not None:
        d["sub_entries"] = sub_entries
    return d


def _full_snapshot(**overrides: Any) -> Dict[str, Any]:
    """Build a fully populated snapshot with sensible defaults."""
    snap: Dict[str, Any] = {
        "history_active": {
            "turns": [
                _make_turn_dict("t-1", "Hi there", 1_700_000_000_000, 1),
                _make_turn_dict("t-2", "How are you?", 1_700_000_001_000, 2),
            ],
        },
        "beliefs_active": {
            "mentioned_entities": [
                {
                    "type": "PERSON",
                    "display_name": "Mom",
                    "person_id": "person_mom",
                    "confidence": 1.0,
                },
            ],
        },
        "affective_now": {
            "dimensions": {"valence": 0.7, "arousal": 0.3, "dominance": 0.5},
        },
        "affective_baseline": {
            "dimensions": {"valence": 0.0, "arousal": 0.2, "dominance": 0.5},
        },
        "scoreboard": {
            "topic_stack": [
                {"name": "dinner", "salience": 0.9},
                {"name": "family", "salience": 0.6},
            ],
        },
        "narrative_active": {"arc_position": "RISING_ACTION", "primary_thread": "evening_plans"},
        "control": {"intents": ["log_memory"]},
        "persona": {"traits": ["warm"]},
        "ifl": {"device_id": "phone-01"},
        "task_state": {"active_goals": ["plan_dinner"]},
        "meta": {"session_id": "sess-from-meta"},
    }
    snap.update(overrides)
    return snap


# ===========================================================================
# TestMWSessionReader
# ===========================================================================


class TestMWSessionReader:
    @pytest.mark.asyncio
    async def test_reads_all_non_skipped_sections(self):
        data = {"beliefs_active": {"x": 1}, "telemetry": {"y": 2}, "meta": {"z": 3}}
        port = FakeSessionReadPort(data)
        config = MWConfig()
        reader = MWSessionReader(port, config)
        snap = await reader.read_snapshot()
        # telemetry is in skip_sections
        assert "beliefs_active" in snap
        assert "meta" in snap
        assert "telemetry" not in snap
        assert port.last_exclude == config.skip_sections

    @pytest.mark.asyncio
    async def test_mw02_latency_enforcement(self):
        """Slow read exceeding 1ms triggers InvariantViolation."""
        port = FakeSessionReadPort({"a": 1}, latency_ns=5_000_000)  # 5ms
        reader = MWSessionReader(port, MWConfig())
        with pytest.raises(InvariantViolation, match="MW-02"):
            await reader.read_snapshot()

    @pytest.mark.asyncio
    async def test_mw02_fast_read_passes(self):
        port = FakeSessionReadPort({"beliefs_active": {"x": 1}})
        reader = MWSessionReader(port, MWConfig())
        snap = await reader.read_snapshot()
        assert snap == {"beliefs_active": {"x": 1}}

    @pytest.mark.asyncio
    async def test_empty_snapshot(self):
        port = FakeSessionReadPort({})
        reader = MWSessionReader(port, MWConfig())
        snap = await reader.read_snapshot()
        assert snap == {}


# ===========================================================================
# TestMWSessionReaderEnriched (B3 — cold-archive merge for session-batch)
# ===========================================================================


class _EnrichedFakePort(FakeSessionReadPort):
    """Fake that returns canned archived turns from read_archived_history."""

    def __init__(
        self,
        snapshot_data: Optional[Dict[str, Any]] = None,
        archived_turns: Optional[List[Dict[str, Any]]] = None,
        raise_archive: bool = False,
    ) -> None:
        super().__init__(snapshot_data)
        self._archived = archived_turns or []
        self._raise_archive = raise_archive
        self.archived_calls = 0
        self.last_session_id: Optional[str] = None
        self.last_limit: Optional[int] = None

    async def read_archived_history(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        self.archived_calls += 1
        self.last_session_id = session_id
        self.last_limit = limit
        if self._raise_archive:
            raise RuntimeError("cold down")
        return list(self._archived)


class TestMWSessionReaderEnriched:
    @pytest.mark.asyncio
    async def test_falls_back_when_no_archive(self):
        """No archived turns -> returns plain snapshot unchanged."""
        port = _EnrichedFakePort({"meta": {"session_id": "s1"}}, archived_turns=[])
        reader = MWSessionReader(port, MWConfig())
        snap = await reader.read_snapshot_enriched("sess-x")
        assert snap == {"meta": {"session_id": "s1"}}
        assert port.last_session_id == "sess-x"

    @pytest.mark.asyncio
    async def test_archive_failure_returns_plain(self):
        """If archive fetch raises, the plain snapshot is returned (never raises)."""
        port = _EnrichedFakePort({"meta": {}}, raise_archive=True)
        reader = MWSessionReader(port, MWConfig())
        snap = await reader.read_snapshot_enriched("sess-x")
        assert "history_active" not in snap or "enriched_from_cold" not in snap.get(
            "history_active", {}
        )

    @pytest.mark.asyncio
    async def test_merges_cold_before_live(self):
        """Cold-archive turns are placed before live hot turns; deduped by turn_id."""
        live_turns = [
            {"turn_id": "t-2", "user_message": "live2", "assistant_response": "a2", "turn_number": 2},
            {"turn_id": "t-3", "user_message": "live3", "assistant_response": "a3", "turn_number": 3},
        ]
        archived_turns = [
            {"turn_id": "t-1", "user_message": "old1", "assistant_response": "oa1", "turn_number": 1},
            {"turn_id": "t-2", "user_message": "old2", "assistant_response": "oa2", "turn_number": 2},  # duplicate
        ]
        port = _EnrichedFakePort(
            {"history_active": {"turns": live_turns}},
            archived_turns=archived_turns,
        )
        reader = MWSessionReader(port, MWConfig())
        snap = await reader.read_snapshot_enriched("sess-x")
        merged = snap["history_active"]["turns"]
        ids = [t["turn_id"] for t in merged]
        # cold t-1, then live t-2 (not dup), then live t-3
        assert ids == ["t-1", "t-2", "t-3"]
        # Live wins for dup t-2 (user_message == "live2", not "old2").
        t2 = next(t for t in merged if t["turn_id"] == "t-2")
        assert t2["user_message"] == "live2"
        assert snap["history_active"]["enriched_from_cold"] is True

    @pytest.mark.asyncio
    async def test_creates_history_section_if_missing(self):
        """If hot snapshot has no history_active, archived turns still land."""
        archived_turns = [
            {"turn_id": "t-1", "user_message": "old1", "assistant_response": "oa1", "turn_number": 1},
        ]
        port = _EnrichedFakePort({}, archived_turns=archived_turns)
        reader = MWSessionReader(port, MWConfig())
        snap = await reader.read_snapshot_enriched("sess-x")
        assert snap["history_active"]["turns"][0]["turn_id"] == "t-1"
        assert snap["history_active"]["enriched_from_cold"] is True


# ===========================================================================
# TestContextBuilderHistory
# ===========================================================================


class TestContextBuilderHistory:
    def test_extracts_current_turn_from_payload(self):
        payload = _make_payload(turn_id="turn-99", user_message="Hello", turn_number=5)
        builder = ContextBuilder(MWConfig())
        ctx = builder.build({"meta": {"session_id": "s1"}}, payload)
        assert ctx.current_turn.turn_id == "turn-99"
        assert ctx.current_turn.text == "Hello"
        assert ctx.current_turn.turn_number == 5

    def test_extracts_all_turns_from_history(self):
        turns = [_make_turn_dict(f"t-{i}", f"msg {i}", turn_number=i) for i in range(1, 6)]
        snap = {"history_active": {"turns": turns}}
        payload = _make_payload()
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, payload)
        assert len(ctx.recent_turns) == 5
        for i, ct in enumerate(ctx.recent_turns, 1):
            assert ct.turn_id == f"t-{i}"

    def test_empty_history(self):
        builder = ContextBuilder(MWConfig())
        ctx = builder.build({}, _make_payload())
        assert ctx.recent_turns == []
        assert ctx.current_turn.turn_id == "turn-99"

    def test_turn_ordering_preserved(self):
        turns = [
            _make_turn_dict("t-3", "c", turn_number=3),
            _make_turn_dict("t-1", "a", turn_number=1),
            _make_turn_dict("t-2", "b", turn_number=2),
        ]
        snap = {"history_active": {"turns": turns}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        ids = [ct.turn_id for ct in ctx.recent_turns]
        assert ids == ["t-3", "t-1", "t-2"]  # preserved, not sorted

    def test_large_window_all_included(self):
        turns = [_make_turn_dict(f"t-{i}", f"msg {i}", turn_number=i) for i in range(1, 26)]
        snap = {"history_active": {"turns": turns}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert len(ctx.recent_turns) == 25

    # ------------------------------------------------------------------
    # A2: assistant_response is loaded as a paired CompressedTurn
    # ------------------------------------------------------------------

    def test_assistant_response_emits_paired_turn(self):
        """Each Turn with both sides emits user + assistant CompressedTurns."""
        snap = {
            "history_active": {
                "turns": [
                    {
                        "turn_id": "t-1",
                        "user_message": "Hi",
                        "assistant_response": "Hello there!",
                        "timestamp_ms": 1_700_000_000_000,
                        "turn_number": 1,
                    },
                ],
            },
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert len(ctx.recent_turns) == 2
        assert ctx.recent_turns[0].role == "user"
        assert ctx.recent_turns[0].text == "Hi"
        assert ctx.recent_turns[1].role == "assistant"
        assert ctx.recent_turns[1].text == "Hello there!"
        # paired ordering: user immediately followed by its assistant
        assert ctx.recent_turns[1].turn_number == ctx.recent_turns[0].turn_number

    def test_empty_assistant_response_skipped(self):
        """Turns with no assistant_response yield only the user CompressedTurn."""
        snap = {
            "history_active": {
                "turns": [
                    {
                        "turn_id": "t-1",
                        "user_message": "Just user",
                        "assistant_response": "",
                        "timestamp_ms": 1,
                        "turn_number": 1,
                    },
                ],
            },
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert len(ctx.recent_turns) == 1
        assert ctx.recent_turns[0].role == "user"

    def test_full_dialogue_window(self):
        """3-turn dialogue → 6 CompressedTurns interleaved user/assistant."""
        snap = {
            "history_active": {
                "turns": [
                    {
                        "turn_id": f"t-{i}",
                        "user_message": f"u{i}",
                        "assistant_response": f"a{i}",
                        "timestamp_ms": i,
                        "turn_number": i,
                    }
                    for i in range(1, 4)
                ],
            },
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        roles = [ct.role for ct in ctx.recent_turns]
        texts = [ct.text for ct in ctx.recent_turns]
        assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]
        assert texts == ["u1", "a1", "u2", "a2", "u3", "a3"]


# ===========================================================================
# TestContextBuilderToolCalls
# ===========================================================================


class TestContextBuilderToolCalls:
    def test_extracts_from_turn_metadata(self):
        tc = [{"name": "search", "status": "success"}]
        turns = [_make_turn_dict("t-1", "search it", turn_number=1, metadata={"tool_calls": tc})]
        snap = {"history_active": {"turns": turns}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert 1 in ctx.tool_calls_per_turn
        assert ctx.tool_calls_per_turn[1] == tc

    def test_extracts_from_sub_entries(self):
        sub = [{"metadata": {"tool_calls": [{"name": "calc", "status": "ok"}]}}]
        turns = [_make_turn_dict("t-1", "calculate", turn_number=1, sub_entries=sub)]
        snap = {"history_active": {"turns": turns}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert 1 in ctx.tool_calls_per_turn
        assert ctx.tool_calls_per_turn[1][0]["name"] == "calc"

    def test_no_tool_calls(self):
        turns = [_make_turn_dict("t-1", "hello", turn_number=1)]
        snap = {"history_active": {"turns": turns}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.tool_calls_per_turn == {}

    def test_mixed_turns(self):
        tc = [{"name": "weather", "status": "ok"}]
        turns = [
            _make_turn_dict("t-1", "weather?", turn_number=1, metadata={"tool_calls": tc}),
            _make_turn_dict("t-2", "thanks", turn_number=2),
        ]
        snap = {"history_active": {"turns": turns}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert 1 in ctx.tool_calls_per_turn
        assert 2 not in ctx.tool_calls_per_turn


# ===========================================================================
# TestContextBuilderAffect
# ===========================================================================


class TestContextBuilderAffect:
    def test_extracts_affect_from_dimensions(self):
        snap = {"affective_now": {"dimensions": {"valence": 0.8, "arousal": 0.4, "dominance": 0.6}}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.current_affect == Affect(valence=0.8, arousal=0.4, dominance=0.6)

    def test_missing_affective_section(self):
        builder = ContextBuilder(MWConfig())
        ctx = builder.build({}, _make_payload())
        assert ctx.current_affect is None

    def test_baseline_and_current(self):
        snap = {
            "affective_now": {"dimensions": {"valence": 0.5, "arousal": 0.3, "dominance": 0.5}},
            "affective_baseline": {
                "dimensions": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5}
            },
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.current_affect is not None
        assert ctx.baseline_affect is not None
        assert ctx.current_affect.valence == 0.5
        assert ctx.baseline_affect.valence == 0.0


# ===========================================================================
# TestContextBuilderTopics
# ===========================================================================


class TestContextBuilderTopics:
    def test_extracts_topic_names(self):
        snap = {"scoreboard": {"topic_stack": [{"name": "dinner", "salience": 0.9}]}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.active_topics == ["dinner"]

    def test_extracts_salience(self):
        snap = {
            "scoreboard": {
                "topic_stack": [
                    {"name": "dinner", "salience": 0.9},
                    {"name": "family", "salience": 0.6},
                ]
            }
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.topic_salience == {"dinner": 0.9, "family": 0.6}

    def test_empty_scoreboard(self):
        snap = {"scoreboard": {}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.active_topics == []
        assert ctx.topic_salience == {}

    def test_missing_scoreboard_section(self):
        builder = ContextBuilder(MWConfig())
        ctx = builder.build({}, _make_payload())
        assert ctx.active_topics == []
        assert ctx.topic_salience == {}


# ===========================================================================
# TestContextBuilderIntegrated
# ===========================================================================


class TestContextBuilderIntegrated:
    def test_full_build_all_sections(self):
        snap = _full_snapshot()
        payload = _make_payload()
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, payload)
        # Core assertions on populated context
        assert ctx.current_turn.turn_id == "turn-99"
        assert len(ctx.recent_turns) == 2
        assert "Mom" in ctx.active_persons
        assert ctx.current_affect is not None
        assert ctx.baseline_affect is not None
        assert ctx.active_topics == ["dinner", "family"]
        assert ctx.active_narrative is not None
        assert ctx.control_context == {"intents": ["log_memory"]}
        assert ctx.device_context == {"device_id": "phone-01"}
        assert ctx.persona_context == {"traits": ["warm"]}
        assert ctx.active_goals == ["plan_dinner"]
        assert ctx.session_id == "sess-from-meta"
        assert ctx.conversation_turn == 5

    def test_missing_sections_graceful(self):
        snap = {"history_active": {"turns": []}, "meta": {"session_id": "s1"}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert ctx.session_id == "s1"
        assert ctx.current_affect is None
        assert ctx.active_topics == []
        assert ctx.active_persons == {}

    def test_temporal_spatial_from_payload(self):
        payload = _make_payload(
            mentioned_time_raw="yesterday",
            mentioned_time_resolved_ms=1_699_913_600_000,
            mentioned_time_confidence=0.95,
            mentioned_location_raw="home",
            mentioned_location_type="home",
            mentioned_location_confidence=0.99,
        )
        builder = ContextBuilder(MWConfig())
        ctx = builder.build({}, payload)
        assert ctx.mentioned_time_raw == "yesterday"
        assert ctx.mentioned_time_resolved_ms == 1_699_913_600_000
        assert ctx.mentioned_location_raw == "home"

    def test_temporal_spatial_fallback_to_beliefs(self):
        payload = _make_payload()  # no temporal/spatial fields set
        snap = {
            "beliefs_active": {
                "mentioned_time": {
                    "raw_text": "last week",
                    "resolved_ms": 1_699_000_000_000,
                    "confidence": 0.8,
                    "is_relative": True,
                },
                "mentioned_location": {
                    "raw_text": "office",
                    "location_type": "office",
                    "entity_id": "loc_office",
                    "confidence": 0.7,
                },
            }
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, payload)
        assert ctx.mentioned_time_raw == "last week"
        assert ctx.mentioned_location_raw == "office"

    def test_persons_extraction(self):
        snap = {
            "beliefs_active": {
                "mentioned_entities": [
                    {
                        "type": "PERSON",
                        "display_name": "Dad",
                        "person_id": "person_dad",
                        "confidence": 0.95,
                    },
                    {"type": "LOCATION", "display_name": "Home", "entity_id": "loc_home"},
                ],
            }
        }
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload())
        assert "Dad" in ctx.active_persons
        assert ctx.active_persons["Dad"]["person_id"] == "person_dad"
        assert "Home" not in ctx.active_persons  # only PERSON type

    def test_session_id_from_meta_or_payload(self):
        # meta.session_id takes priority
        snap = {"meta": {"session_id": "from-meta"}}
        builder = ContextBuilder(MWConfig())
        ctx = builder.build(snap, _make_payload(session_id="from-payload"))
        assert ctx.session_id == "from-meta"

        # Fallback to payload when meta is missing
        ctx2 = builder.build({}, _make_payload(session_id="from-payload"))
        assert ctx2.session_id == "from-payload"
