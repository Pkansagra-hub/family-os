"""StructuredEpisodeSummary -- rich JSON schema for episode_summary column (M9.6).

Replaces plain-text pipe-delimited summaries with actionable structure.
All fields derived from existing event metadata -- no LLM.
Stored as TEXT (JSON-serialized) in st_epi.episode_summary.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0"


@dataclass
class EventRecord:
    """Per-event record within the structured summary."""

    event_id: str
    timestamp_ms: int
    text_preview: str  # first 200 chars
    sentiment_label: str | None = None
    dominant_emotion: str | None = None
    intent: str | None = None
    salience_band: str | None = None
    ingress_channel: str | None = None


@dataclass
class StructuredEpisodeSummary:
    """Rich structured JSON for episode_summary column.

    Stored as TEXT in st_epi.episode_summary.
    Reuses existing column -- no schema migration needed.
    """

    schema_version: str = SCHEMA_VERSION
    title: str = ""
    event_count: int = 0
    dominant_thread_id: str | None = None
    thread_distribution: dict[str, int] = field(default_factory=dict)
    goal_distribution: dict[str, int] = field(default_factory=dict)
    temporal_narrative: str = ""
    participants: list[str] = field(default_factory=list)
    affect_trajectory: list[dict[str, Any]] = field(default_factory=list)
    dominant_sentiment: str | None = None
    dominant_emotion: str | None = None
    location_context: str | None = None
    activity_type: str | None = None
    event_records: list[EventRecord] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, raw: str) -> StructuredEpisodeSummary:
        data = json.loads(raw)
        events = [EventRecord(**e) for e in data.pop("event_records", [])]
        return cls(**data, event_records=events)


def _first_emotion(emotions_json: Any) -> str | None:
    """Extract first emotion from emotions_json (string or dict)."""
    if not emotions_json:
        return None
    if isinstance(emotions_json, str):
        try:
            data = json.loads(emotions_json)
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        data = emotions_json
    if isinstance(data, dict):
        if data:
            return max(data, key=lambda k: float(data[k] or 0))
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first.get("label") or first.get("emotion")
        return str(first)
    return None


def _mode(items: list[str]) -> str | None:
    """Return most common item or None."""
    if not items:
        return None
    counter = Counter(items)
    return counter.most_common(1)[0][0]


def _collect_participants(evt: dict[str, Any], out: set[str]) -> None:
    """Extract participant names from event dict."""
    p_json = evt.get("participants_json") or "[]"
    try:
        p_list = json.loads(p_json) if isinstance(p_json, str) else p_json
        for p in p_list:
            if isinstance(p, str) and p.strip():
                out.add(p.strip())
    except (json.JSONDecodeError, TypeError):
        pass


def _build_temporal_narrative(
    event_records: list[EventRecord],
    record_data: dict[str, Any],
) -> str:
    """Build human-readable temporal description."""
    if not event_records:
        return ""

    start_ms = record_data.get("start_time_utc") or (
        event_records[0].timestamp_ms if event_records else 0
    )
    end_ms = record_data.get("end_time_utc") or (
        event_records[-1].timestamp_ms if event_records else 0
    )

    if not start_ms:
        return ""

    import datetime

    try:
        start_dt = datetime.datetime.fromtimestamp(start_ms / 1000, tz=datetime.timezone.utc)
    except (OSError, ValueError, OverflowError):
        return ""

    hour = start_dt.hour
    if 5 <= hour < 12:
        tod = "Morning"
    elif 12 <= hour < 17:
        tod = "Afternoon"
    elif 17 <= hour < 21:
        tod = "Evening"
    else:
        tod = "Night"

    day_name = start_dt.strftime("%A")
    time_str = start_dt.strftime("%H:%M")

    parts = [f"{tod} episode"]

    if end_ms and end_ms > start_ms:
        dur_min = (end_ms - start_ms) / 60_000
        if dur_min >= 60:
            h = int(dur_min // 60)
            m = int(dur_min % 60)
            parts[0] += f" ({h}h {m}min)" if m else f" ({h}h)"
        elif dur_min >= 1:
            parts[0] += f" ({int(dur_min)}min)"

    parts.append(f"{day_name} {time_str}")

    return ", ".join(parts)


def build_structured_summary(
    events: list[dict[str, Any]],
    record_data: dict[str, Any],
) -> StructuredEpisodeSummary:
    """Build StructuredEpisodeSummary from event rows + episode record_data.

    Args:
        events: List of st_hipp_events rows (dicts) for member events.
        record_data: Episode record_data from StagedWrite.

    Returns:
        StructuredEpisodeSummary with all derivable fields populated.
    """
    event_records: list[EventRecord] = []
    affect_trajectory: list[dict[str, Any]] = []
    thread_counts: dict[str, int] = {}
    goal_counts: dict[str, int] = {}
    sentiments: list[str] = []
    emotions: list[str] = []
    participants_set: set[str] = set()

    for evt in events:
        ts = evt.get("conversation_anchor_ms") or evt.get("event_time_utc", 0)

        event_records.append(
            EventRecord(
                event_id=evt.get("event_id", ""),
                timestamp_ms=ts,
                text_preview=(evt.get("user_message") or "")[:200],
                sentiment_label=evt.get("sentiment_label"),
                dominant_emotion=_first_emotion(evt.get("emotions_json")),
                intent=evt.get("intent_ultrabert"),
                salience_band=evt.get("salience_band"),
                ingress_channel=evt.get("ingress_channel"),
            )
        )

        if evt.get("affect_valence") is not None:
            affect_trajectory.append(
                {
                    "timestamp_ms": ts,
                    "valence": evt.get("affect_valence"),
                    "arousal": evt.get("affect_arousal"),
                    "emotion": _first_emotion(evt.get("emotions_json")),
                }
            )

        thread_id = evt.get("narrative_thread_id")
        if thread_id:
            thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1

        goal = evt.get("intent_ultrabert")
        if goal:
            goal_counts[goal] = goal_counts.get(goal, 0) + 1

        sl = evt.get("sentiment_label")
        if sl:
            sentiments.append(sl)
        em = _first_emotion(evt.get("emotions_json"))
        if em:
            emotions.append(em)

        _collect_participants(evt, participants_set)

    event_records.sort(key=lambda e: e.timestamp_ms)
    affect_trajectory.sort(key=lambda a: a.get("timestamp_ms", 0))

    temporal_narrative = _build_temporal_narrative(event_records, record_data)
    dominant_thread = max(thread_counts, key=thread_counts.get) if thread_counts else None

    return StructuredEpisodeSummary(
        title=record_data.get("episode_summary") or record_data.get("title", ""),
        event_count=len(events),
        dominant_thread_id=dominant_thread,
        thread_distribution=thread_counts,
        goal_distribution=goal_counts,
        temporal_narrative=temporal_narrative,
        participants=sorted(participants_set),
        affect_trajectory=affect_trajectory,
        dominant_sentiment=_mode(sentiments),
        dominant_emotion=_mode(emotions),
        location_context=record_data.get("primary_location"),
        activity_type=record_data.get("activity_type_ultrabert") or record_data.get("episode_type"),
        event_records=event_records,
    )
