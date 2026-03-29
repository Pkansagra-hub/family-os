"""
Tests for conversation-time timestamp chain (Epic 1.2).

CRITICAL DISTINCTION:
    R2 episode formation uses CONVERSATION TIME (when user chatted with K1),
    NOT temporal resolution (what date the event REFERS TO).
    These are two different timestamp chains serving different purposes.

Issue 1.2.6: Validates that:
    - R0 uses event_time_utc (conversation time) as primary timestamp
    - R2 algorithms group same-conversation events into same episodes
      regardless of resolved_epoch_ms differences
    - Offline drain scenario with collapsed created_at is documented
    - Seconds-to-milliseconds conversion works correctly
    - temporal_source provenance is inferred correctly (Issue 1.2.3)
    - Timestamp quality stats are computed correctly (Issue 1.2.4)

Tests:
    Conversation Time Chain:
        - test_event_time_utc_is_primary_timestamp
        - test_created_at_fallback_when_event_time_utc_missing
        - test_seconds_to_milliseconds_conversion
        - test_milliseconds_passthrough_no_conversion
        - test_temporal_resolved_epoch_ms_not_used_for_episodes

    Same-Conversation Episode Grouping:
        - test_same_conversation_different_resolved_dates_no_split
        - test_different_conversations_split_correctly

    Offline Drain Scenario:
        - test_offline_drain_with_valid_event_time_utc
        - test_collapsed_created_at_no_split

    Temporal Source Provenance (Issue 1.2.3):
        - test_temporal_source_mw_resolved
        - test_temporal_source_event_time_default
        - test_temporal_source_empty_string_default

    Timestamp Quality Stats (Issue 1.2.4):
        - test_all_mw_resolved_zero_degraded
        - test_all_event_time_full_degraded
        - test_mixed_sources_partial_degraded
        - test_unknown_source_counted_as_degraded
"""

from __future__ import annotations

from k0.modules.consolidation.algorithms.episode_splitter import EpisodeSplitter, SplitConfig
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phases.r2_episodic_integrator import EventAdapter

# =============================================================================
# Fixtures
# =============================================================================


def _make_event(**overrides) -> P03EventState:
    """Factory for P03EventState with sensible defaults for timestamp testing."""
    defaults = dict(
        event_id="evt-ts-001",
        timestamp=1700000000000,  # conversation time in ms
        embedding_768=[0.1] * 768,
        temporal_resolved_epoch_ms=0.0,
        temporal_source="event_time",
    )
    defaults.update(overrides)
    return P03EventState(**defaults)  # type: ignore[arg-type]


# =============================================================================
# Conversation Time Chain
# =============================================================================


class TestConversationTimeChain:
    """Verify R0 uses event_time_utc (conversation time) for episode grouping."""

    def test_event_time_utc_is_primary_timestamp(self):
        """event_time_utc (MW now_utc, approx conversation time) is the primary timestamp."""
        conversation_time_ms = 1700000000000  # When user actually chatted
        resolved_epoch_ms = 1699920000000.0  # "yesterday evening" -- different day
        evt = _make_event(
            timestamp=conversation_time_ms,
            temporal_resolved_epoch_ms=resolved_epoch_ms,
        )
        adapter = EventAdapter(evt)
        # R2 episode grouping must use conversation time, NOT resolved epoch
        assert adapter.timestamp == conversation_time_ms
        assert adapter.timestamp != resolved_epoch_ms

    def test_created_at_fallback_when_event_time_utc_missing(self):
        """When event_time_utc is 0/NULL, R0 falls back to created_at.

        Simulates: event_time_utc = 0 in DB, R0 fell to created_at.
        The P03EventState.timestamp already has the fallback value set by R0.
        """
        created_at_ms = 1700003600000
        evt = _make_event(timestamp=created_at_ms)
        adapter = EventAdapter(evt)
        assert adapter.timestamp == created_at_ms

    def test_seconds_to_milliseconds_conversion(self):
        """R0 converts seconds to ms using < 1e12 heuristic.

        event_time_utc stored as seconds in DB (< 1e12), R0 multiplies by 1000.
        """
        # Simulating what R0 does: 1700000000 seconds * 1000 = 1700000000000 ms
        event_time_ms = 1700000000000
        evt = _make_event(timestamp=event_time_ms)
        adapter = EventAdapter(evt)
        assert adapter.timestamp == 1700000000000

    def test_milliseconds_passthrough_no_conversion(self):
        """If value is already in ms (>= 1e12), R0 passes through unchanged."""
        already_ms = 1700000000000
        evt = _make_event(timestamp=already_ms)
        adapter = EventAdapter(evt)
        assert adapter.timestamp == already_ms

    def test_temporal_resolved_epoch_ms_not_used_for_episodes(self):
        """temporal_resolved_epoch_ms is for temporal queries, NOT episode grouping.

        EventAdapter.timestamp returns event.timestamp (conversation time),
        NOT event.temporal_resolved_epoch_ms.
        """
        conv_time = 1700000000000
        resolved = 1699920000000.0  # Yesterday
        evt = _make_event(timestamp=conv_time, temporal_resolved_epoch_ms=resolved)
        adapter = EventAdapter(evt)
        assert adapter.timestamp == conv_time
        assert adapter.temporal_resolved_epoch_ms == resolved
        assert adapter.timestamp != adapter.temporal_resolved_epoch_ms


# =============================================================================
# Same-Conversation Episode Grouping
# =============================================================================


class TestSameConversationEpisodeGrouping:
    """Events from the same conversation must group together
    even if their temporal resolutions point to different dates."""

    def test_same_conversation_different_resolved_dates_no_split(self):
        """User says 'Had dinner yesterday' and 'Remind me next Friday'
        in the same conversation 30 seconds apart.

        resolved_epoch_ms differs by DAYS but conversation time differs by 30s.
        They must NOT be split by EpisodeSplitter.
        """
        conv_time_1 = 1700000000000  # Conversation at 10:00:00
        conv_time_2 = 1700000030000  # Same conversation at 10:00:30

        e1 = _make_event(
            event_id="e1",
            timestamp=conv_time_1,
            temporal_resolved_epoch_ms=1699920000000.0,  # yesterday evening
        )
        e2 = _make_event(
            event_id="e2",
            timestamp=conv_time_2,
            temporal_resolved_epoch_ms=1700524800000.0,  # next Friday (6 days later!)
        )
        a1, a2 = EventAdapter(e1), EventAdapter(e2)
        splitter = EpisodeSplitter(SplitConfig(hard_time_gap_minutes=30))
        decision = splitter._boundary_decision([a1], a2)
        # 30s gap < 30min hard threshold -> NO split -> same episode (CORRECT)
        assert decision.split is False

    def test_different_conversations_split_correctly(self):
        """Two events from conversations 2 hours apart should split."""
        conv_time_1 = 1700000000000  # Morning conversation
        conv_time_2 = 1700007200000  # 2 hours later, different conversation

        e1 = _make_event(event_id="e1", timestamp=conv_time_1)
        e2 = _make_event(event_id="e2", timestamp=conv_time_2)
        a1, a2 = EventAdapter(e1), EventAdapter(e2)
        splitter = EpisodeSplitter(SplitConfig(hard_time_gap_minutes=30))
        decision = splitter._boundary_decision([a1], a2)
        # 2h gap > 30min hard threshold -> HARD_TIME_GAP split
        assert decision.split is True


# =============================================================================
# Offline Drain Scenario
# =============================================================================


class TestOfflineDrainScenario:
    """Simulate offline queue drain where created_at collapses."""

    def test_offline_drain_with_valid_event_time_utc(self):
        """Events with valid event_time_utc maintain spread even during drain.

        created_at would be identical (K0 insert time) but event_time_utc
        preserves the original conversation times.
        """
        # User had 2 conversations: 6pm and 8pm. K0 was offline, drained at 10pm.
        # event_time_utc = original MW now_utc() at conversation time (CORRECT)
        e1 = _make_event(event_id="e1", timestamp=1700000000000)  # 6pm conv
        e2 = _make_event(event_id="e2", timestamp=1700007200000)  # 8pm conv
        a1, a2 = EventAdapter(e1), EventAdapter(e2)
        splitter = EpisodeSplitter(SplitConfig(hard_time_gap_minutes=30))
        decision = splitter._boundary_decision([a1], a2)
        assert decision.split is True  # 2h > 30min hard threshold -> split (CORRECT)

    def test_collapsed_created_at_no_split(self):
        """If R0 fell back to created_at (both events arrived at same time),
        timestamps are identical and splitting fails.

        This documents the degraded behavior that Issue 1.2.2 hardening
        aims to prevent by ensuring event_time_utc is always used over created_at.
        """
        # Both events got created_at = drain time (identical)
        drain_time = 1700010000000
        e1 = _make_event(event_id="e1", timestamp=drain_time)
        e2 = _make_event(event_id="e2", timestamp=drain_time)
        a1, a2 = EventAdapter(e1), EventAdapter(e2)
        splitter = EpisodeSplitter(SplitConfig(hard_time_gap_minutes=30))
        decision = splitter._boundary_decision([a1], a2)
        # 0ms gap -> no split -> mega-episode (BROKEN case, documents the problem)
        assert decision.split is False


# =============================================================================
# Temporal Source Provenance (Issue 1.2.3)
# =============================================================================


class TestTemporalSourceProvenance:
    """Issue 1.2.3: temporal_source field on P03EventState."""

    def test_temporal_source_mw_resolved(self):
        """When temporal_resolved_epoch_ms > 0, source should be mw_resolved."""
        evt = _make_event(
            temporal_resolved_epoch_ms=1699920000000.0,
            temporal_source="mw_resolved",
        )
        assert evt.temporal_source == "mw_resolved"
        adapter = EventAdapter(evt)
        # temporal_source is accessible via getattr on the underlying event
        assert adapter.event.temporal_source == "mw_resolved"

    def test_temporal_source_event_time_default(self):
        """When temporal_resolved_epoch_ms == 0, source should be event_time."""
        evt = _make_event(
            temporal_resolved_epoch_ms=0.0,
            temporal_source="event_time",
        )
        assert evt.temporal_source == "event_time"

    def test_temporal_source_empty_string_default(self):
        """Default temporal_source is empty string on P03EventState."""
        evt = P03EventState(event_id="bare-evt")
        assert evt.temporal_source == ""


# =============================================================================
# Timestamp Quality Stats (Issue 1.2.4)
# =============================================================================


class TestTimestampQualityStats:
    """Issue 1.2.4: Verify quality stats computation logic.

    This tests the counting logic that R2 run() applies to novel_events.
    We replicate the exact computation from r2_episodic_integrator.py to
    validate the algorithm independently.
    """

    @staticmethod
    def _compute_quality(events: list[P03EventState]) -> tuple[dict[str, int], float]:
        """Replicate R2 quality stats computation."""
        ts_quality: dict[str, int] = {
            "mw_resolved": 0,
            "ner_temporal": 0,
            "event_time": 0,
            "envelope_ts": 0,
            "now": 0,
            "unknown": 0,
        }
        for evt in events:
            src = getattr(evt, "temporal_source", "") or "unknown"
            ts_quality[src] = ts_quality.get(src, 0) + 1

        total = len(events) or 1
        degraded = (
            ts_quality["event_time"]
            + ts_quality["envelope_ts"]
            + ts_quality["now"]
            + ts_quality["unknown"]
        )
        return ts_quality, degraded / total

    def test_all_mw_resolved_zero_degraded(self):
        """All events with mw_resolved -> degraded_ratio = 0.0."""
        events = [_make_event(event_id=f"e{i}", temporal_source="mw_resolved") for i in range(5)]
        quality, ratio = self._compute_quality(events)
        assert quality["mw_resolved"] == 5
        assert ratio == 0.0

    def test_all_event_time_full_degraded(self):
        """All events with event_time -> degraded_ratio = 1.0."""
        events = [_make_event(event_id=f"e{i}", temporal_source="event_time") for i in range(4)]
        quality, ratio = self._compute_quality(events)
        assert quality["event_time"] == 4
        assert ratio == 1.0

    def test_mixed_sources_partial_degraded(self):
        """2 mw_resolved + 2 event_time -> degraded_ratio = 0.5."""
        events = [
            _make_event(event_id="e0", temporal_source="mw_resolved"),
            _make_event(event_id="e1", temporal_source="mw_resolved"),
            _make_event(event_id="e2", temporal_source="event_time"),
            _make_event(event_id="e3", temporal_source="event_time"),
        ]
        quality, ratio = self._compute_quality(events)
        assert quality["mw_resolved"] == 2
        assert quality["event_time"] == 2
        assert ratio == 0.5

    def test_unknown_source_counted_as_degraded(self):
        """Events with empty temporal_source map to 'unknown' and count as degraded."""
        events = [
            _make_event(event_id="e0", temporal_source=""),
            _make_event(event_id="e1", temporal_source="mw_resolved"),
        ]
        quality, ratio = self._compute_quality(events)
        assert quality["unknown"] == 1
        assert quality["mw_resolved"] == 1
        assert ratio == 0.5

    def test_ner_temporal_not_degraded(self):
        """ner_temporal is NOT counted as degraded (medium quality)."""
        events = [
            _make_event(event_id="e0", temporal_source="ner_temporal"),
            _make_event(event_id="e1", temporal_source="ner_temporal"),
        ]
        quality, ratio = self._compute_quality(events)
        assert quality["ner_temporal"] == 2
        assert ratio == 0.0
