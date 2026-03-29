"""Tests for SummaryRegenerator and StructuredEpisodeSummary (M9.6 D8)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from k0.modules.consolidation.reconciliation.hooks.episode_summary import (
    SCHEMA_VERSION,
    EventRecord,
    StructuredEpisodeSummary,
    _first_emotion,
    _mode,
    build_structured_summary,
)
from k0.modules.consolidation.reconciliation.hooks.summary_regen import SummaryRegenerator

# ---------------------------------------------------------------------------
# Helpers: fake events
# ---------------------------------------------------------------------------


def _event(
    event_id: str = "ev-1",
    ts: int = 1710500000000,
    text: str = "Had lunch with mom",
    sentiment: str = "positive",
    emotion_json: str | None = '{"joy": 0.8, "sadness": 0.1}',
    intent: str | None = "share_experience",
    salience: str | None = "HIGH",
    channel: str | None = "chat",
    valence: float | None = 0.7,
    arousal: float | None = 0.4,
    thread_id: str | None = "thread-1",
    participants: str = '["Mom"]',
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "conversation_anchor_ms": ts,
        "event_time_utc": ts,
        "user_message": text,
        "sentiment_label": sentiment,
        "emotions_json": emotion_json,
        "intent_ultrabert": intent,
        "salience_band": salience,
        "ingress_channel": channel,
        "affect_valence": valence,
        "affect_arousal": arousal,
        "narrative_thread_id": thread_id,
        "participants_json": participants,
    }


def _record_data(
    summary: str = "Test episode",
    start: int = 1710500000000,
    end: int = 1710505400000,
    location: str | None = "Home",
    activity: str | None = "FAMILY_DINNER",
) -> dict[str, Any]:
    return {
        "episode_summary": summary,
        "start_time_utc": start,
        "end_time_utc": end,
        "primary_location": location,
        "activity_type_ultrabert": activity,
    }


# ===========================================================================
# Test: StructuredEpisodeSummary schema
# ===========================================================================


class TestStructuredEpisodeSummarySchema:
    def test_schema_version(self) -> None:
        s = StructuredEpisodeSummary()
        assert s.schema_version == SCHEMA_VERSION
        assert s.schema_version == "1.0"

    def test_default_empty(self) -> None:
        s = StructuredEpisodeSummary()
        assert s.title == ""
        assert s.event_count == 0
        assert s.participants == []
        assert s.affect_trajectory == []
        assert s.event_records == []

    def test_all_fields_present(self) -> None:
        s = StructuredEpisodeSummary(
            title="Family Dinner",
            event_count=3,
            dominant_thread_id="thread-1",
            thread_distribution={"thread-1": 3},
            goal_distribution={"share": 2},
            temporal_narrative="Evening episode (1h 30min), Friday 18:00",
            participants=["Mom", "Dad"],
            affect_trajectory=[{"timestamp_ms": 1000, "valence": 0.8}],
            dominant_sentiment="positive",
            dominant_emotion="joy",
            location_context="Home",
            activity_type="FAMILY_DINNER",
        )
        assert s.event_count == 3
        assert s.dominant_emotion == "joy"
        assert len(s.participants) == 2


# ===========================================================================
# Test: JSON round-trip
# ===========================================================================


class TestJSONRoundTrip:
    def test_roundtrip_simple(self) -> None:
        original = StructuredEpisodeSummary(
            title="Test",
            event_count=2,
            participants=["Alice", "Bob"],
        )
        json_str = original.to_json()
        restored = StructuredEpisodeSummary.from_json(json_str)
        assert restored.title == "Test"
        assert restored.event_count == 2
        assert restored.participants == ["Alice", "Bob"]

    def test_roundtrip_with_events(self) -> None:
        original = StructuredEpisodeSummary(
            title="Full",
            event_count=1,
            event_records=[
                EventRecord(
                    event_id="ev-1",
                    timestamp_ms=1000,
                    text_preview="Hello",
                    sentiment_label="neutral",
                )
            ],
        )
        json_str = original.to_json()
        restored = StructuredEpisodeSummary.from_json(json_str)
        assert len(restored.event_records) == 1
        assert restored.event_records[0].event_id == "ev-1"
        assert restored.event_records[0].text_preview == "Hello"

    def test_roundtrip_preserves_schema_version(self) -> None:
        original = StructuredEpisodeSummary()
        json_str = original.to_json()
        restored = StructuredEpisodeSummary.from_json(json_str)
        assert restored.schema_version == "1.0"

    def test_to_json_is_valid_json(self) -> None:
        s = StructuredEpisodeSummary(title="Test")
        data = json.loads(s.to_json())
        assert isinstance(data, dict)
        assert data["schema_version"] == "1.0"


# ===========================================================================
# Test: build_structured_summary
# ===========================================================================


class TestBuildStructuredSummary:
    def test_empty_events(self) -> None:
        s = build_structured_summary([], _record_data())
        assert s.event_count == 0
        assert s.event_records == []
        assert s.affect_trajectory == []

    def test_single_event(self) -> None:
        events = [_event()]
        s = build_structured_summary(events, _record_data())
        assert s.event_count == 1
        assert len(s.event_records) == 1
        assert s.event_records[0].event_id == "ev-1"
        assert s.event_records[0].text_preview == "Had lunch with mom"

    def test_multiple_events_sorted(self) -> None:
        events = [
            _event(event_id="ev-2", ts=2000),
            _event(event_id="ev-1", ts=1000),
            _event(event_id="ev-3", ts=3000),
        ]
        s = build_structured_summary(events, _record_data())
        assert [e.event_id for e in s.event_records] == ["ev-1", "ev-2", "ev-3"]

    def test_affect_trajectory_populated(self) -> None:
        events = [
            _event(event_id="ev-1", ts=1000, valence=0.8, arousal=0.5),
            _event(event_id="ev-2", ts=2000, valence=-0.3, arousal=0.9),
        ]
        s = build_structured_summary(events, _record_data())
        assert len(s.affect_trajectory) == 2
        assert s.affect_trajectory[0]["valence"] == 0.8
        assert s.affect_trajectory[1]["valence"] == -0.3

    def test_affect_trajectory_sorted_chronologically(self) -> None:
        events = [
            _event(event_id="ev-2", ts=2000, valence=0.5),
            _event(event_id="ev-1", ts=1000, valence=0.8),
        ]
        s = build_structured_summary(events, _record_data())
        assert s.affect_trajectory[0]["timestamp_ms"] == 1000
        assert s.affect_trajectory[1]["timestamp_ms"] == 2000

    def test_no_affect_when_valence_none(self) -> None:
        events = [_event(valence=None, arousal=None)]
        s = build_structured_summary(events, _record_data())
        assert s.affect_trajectory == []

    def test_thread_distribution(self) -> None:
        events = [
            _event(event_id="ev-1", thread_id="t1"),
            _event(event_id="ev-2", thread_id="t1"),
            _event(event_id="ev-3", thread_id="t2"),
        ]
        s = build_structured_summary(events, _record_data())
        assert s.thread_distribution == {"t1": 2, "t2": 1}
        assert s.dominant_thread_id == "t1"

    def test_goal_distribution(self) -> None:
        events = [
            _event(event_id="ev-1", intent="share_experience"),
            _event(event_id="ev-2", intent="share_experience"),
            _event(event_id="ev-3", intent="ask_question"),
        ]
        s = build_structured_summary(events, _record_data())
        assert s.goal_distribution == {"share_experience": 2, "ask_question": 1}

    def test_participants_collected(self) -> None:
        events = [
            _event(event_id="ev-1", participants='["Mom"]'),
            _event(event_id="ev-2", participants='["Dad", "Mom"]'),
        ]
        s = build_structured_summary(events, _record_data())
        assert s.participants == ["Dad", "Mom"]

    def test_dominant_sentiment(self) -> None:
        events = [
            _event(event_id="ev-1", sentiment="positive"),
            _event(event_id="ev-2", sentiment="positive"),
            _event(event_id="ev-3", sentiment="negative"),
        ]
        s = build_structured_summary(events, _record_data())
        assert s.dominant_sentiment == "positive"

    def test_dominant_emotion(self) -> None:
        events = [
            _event(event_id="ev-1", emotion_json='{"joy": 0.9}'),
            _event(event_id="ev-2", emotion_json='{"joy": 0.7}'),
            _event(event_id="ev-3", emotion_json='{"sadness": 0.8}'),
        ]
        s = build_structured_summary(events, _record_data())
        assert s.dominant_emotion == "joy"

    def test_location_from_record_data(self) -> None:
        s = build_structured_summary([_event()], _record_data(location="Thai Restaurant"))
        assert s.location_context == "Thai Restaurant"

    def test_activity_type_from_record_data(self) -> None:
        s = build_structured_summary([_event()], _record_data(activity="FAMILY_DINNER"))
        assert s.activity_type == "FAMILY_DINNER"

    def test_title_from_record_data(self) -> None:
        s = build_structured_summary([_event()], _record_data(summary="Family dinner with mom"))
        assert s.title == "Family dinner with mom"

    def test_text_preview_truncated(self) -> None:
        long_text = "x" * 300
        events = [_event(text=long_text)]
        s = build_structured_summary(events, _record_data())
        assert len(s.event_records[0].text_preview) == 200


# ===========================================================================
# Test: temporal narrative
# ===========================================================================


class TestTemporalNarrative:
    def test_morning_episode(self) -> None:
        # 2024-03-15 09:15 UTC
        events = [_event(ts=1710493200000)]
        s = build_structured_summary(events, _record_data(start=1710493200000, end=1710498600000))
        assert "Morning" in s.temporal_narrative

    def test_evening_episode(self) -> None:
        # 2024-03-15 18:00 UTC
        events = [_event(ts=1710525600000)]
        s = build_structured_summary(events, _record_data(start=1710525600000, end=1710531000000))
        assert "Evening" in s.temporal_narrative

    def test_duration_in_narrative(self) -> None:
        start = 1710493200000
        end = start + 90 * 60 * 1000  # 1h 30min
        events = [_event(ts=start)]
        s = build_structured_summary(events, _record_data(start=start, end=end))
        assert "1h 30min" in s.temporal_narrative

    def test_empty_narrative_no_events(self) -> None:
        s = build_structured_summary([], _record_data())
        assert s.temporal_narrative == ""


# ===========================================================================
# Test: helper functions
# ===========================================================================


class TestHelpers:
    def test_first_emotion_dict(self) -> None:
        assert _first_emotion('{"joy": 0.9, "sadness": 0.1}') == "joy"

    def test_first_emotion_none(self) -> None:
        assert _first_emotion(None) is None

    def test_first_emotion_empty_string(self) -> None:
        assert _first_emotion("") is None

    def test_first_emotion_list(self) -> None:
        assert _first_emotion('[{"label": "joy"}]') == "joy"

    def test_mode_basic(self) -> None:
        assert _mode(["a", "b", "a"]) == "a"

    def test_mode_empty(self) -> None:
        assert _mode([]) is None


# ===========================================================================
# Test: SummaryRegenerator
# ===========================================================================


class FakeTextCoordinator:
    def __init__(self, text: str = "generated-embedding-text"):
        self.text = text
        self.calls: list[dict] = []

    async def process(self, layer, record_data, source_event_ids, conn):
        self.calls.append({"layer": layer, "event_ids": source_event_ids})

        class _Result:
            embedding_text = self.text
            embedding_model = "ultrabert-v2.1.0"
            source_texts_json = '["text1"]'

        return _Result()


class FakeEventFetcher:
    def __init__(self, events: list[dict[str, Any]] | None = None):
        self.events = events or [_event()]
        self.calls: list[list[str]] = []

    async def fetch(self, event_ids, conn):
        self.calls.append(event_ids)
        return self.events


class TestSummaryRegeneratorEpisodic:
    def test_episodic_produces_summary_json(self) -> None:
        regen = SummaryRegenerator(
            text_coordinator=FakeTextCoordinator(),
            event_fetcher=FakeEventFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            regen.regenerate(
                layer="st_epi",
                record_id="ep-1",
                spec=None,
                source_event_ids=["ev-1"],
                record_data=_record_data(),
            )
        )
        assert result.summary_json is not None
        parsed = json.loads(result.summary_json)
        assert parsed["schema_version"] == "1.0"
        assert parsed["event_count"] == 1

    def test_episodic_produces_embedding_text(self) -> None:
        regen = SummaryRegenerator(
            text_coordinator=FakeTextCoordinator("new-text"),
            event_fetcher=FakeEventFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            regen.regenerate("st_epi", "ep-1", None, ["ev-1"], _record_data())
        )
        assert result.embedding_text == "new-text"
        assert result.embedding_model == "ultrabert-v2.1.0"

    def test_episodic_fetches_events(self) -> None:
        fetcher = FakeEventFetcher()
        regen = SummaryRegenerator(
            text_coordinator=FakeTextCoordinator(),
            event_fetcher=fetcher,
        )
        asyncio.get_event_loop().run_until_complete(
            regen.regenerate("st_epi", "ep-1", None, ["ev-1", "ev-2"], _record_data())
        )
        assert fetcher.calls == [["ev-1", "ev-2"]]


class TestSummaryRegeneratorGeneric:
    def test_generic_no_summary_json(self) -> None:
        regen = SummaryRegenerator(
            text_coordinator=FakeTextCoordinator(),
            event_fetcher=FakeEventFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            regen.regenerate("st_sem", "sem-1", None, ["ev-1"], {})
        )
        assert result.summary_json is None
        assert result.embedding_text == "generated-embedding-text"

    def test_generic_calls_coordinator(self) -> None:
        coord = FakeTextCoordinator()
        regen = SummaryRegenerator(
            text_coordinator=coord,
            event_fetcher=FakeEventFetcher(),
        )
        asyncio.get_event_loop().run_until_complete(
            regen.regenerate("st_procedural", "rout-1", None, ["ev-1"], {})
        )
        assert coord.calls[0]["layer"] == "st_procedural"


class TestSummaryRegeneratorNoCoordinator:
    def test_no_coordinator_returns_none_embedding(self) -> None:
        regen = SummaryRegenerator(
            text_coordinator=None,
            event_fetcher=FakeEventFetcher(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            regen.regenerate("st_epi", "ep-1", None, ["ev-1"], _record_data())
        )
        # Summary JSON is still generated from events
        assert result.summary_json is not None
        # But embedding_text is None (no coordinator)
        assert result.embedding_text is None
