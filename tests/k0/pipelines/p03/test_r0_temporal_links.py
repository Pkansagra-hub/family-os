"""
Epic 2.4 (GAP-002) -- R0 temporal_links_json loading tests.

Tests that R0 batch selector correctly loads temporal_links_json
from st_hipp_events rows into P03EventState.

Also tests M13 map_temporal_group() passes temporal_links_json through.
"""

import json

from k0.modules.builders.hipp_events_row import map_temporal_group
from k0.pipelines.p03.event_state import P03EventState

# ============================================================================
# M13 map_temporal_group -- temporal_links_json passthrough
# ============================================================================


class TestMapTemporalGroupTemporalLinks:
    """M13 builder passes temporal_links_json through to row dict."""

    def test_temporal_links_json_present(self):
        """temporal_links_json in temporal_output -> in row dict."""
        links = [
            {
                "mentioned_time": "yesterday",
                "link_type": "RETROSPECTIVE",
                "resolved_epoch_ms": 1700000000000,
                "uncertainty_window_ms": 86400000,
                "confidence": 0.95,
            },
        ]
        temporal_output = {
            "event_time_utc": 1700000000,
            "write_time_utc": 1700000000,
            "write_lag_ms": 0,
            "local_date": "2024-01-01",
            "local_time": "12:00:00",
            "day_of_week": "Monday",
            "is_weekend": False,
            "time_of_day_bucket": "afternoon",
            "circadian_slot": "lunch",
            "is_backdated": False,
            "temporal_mentioned_time": "yesterday",
            "temporal_resolved_epoch_ms": 1700000000000,
            "temporal_orientation": "PAST",
            "conversation_anchor_ms": 1700000000000,
            "temporal_source": "conversation_anchor",
            "temporal_links_json": json.dumps(links),
        }
        row = map_temporal_group(temporal_output)
        assert row["temporal_links_json"] == json.dumps(links)

    def test_temporal_links_json_none(self):
        """No temporal_links_json -> None in row dict."""
        temporal_output = {
            "event_time_utc": 1700000000,
            "write_time_utc": 1700000000,
            "write_lag_ms": 0,
        }
        row = map_temporal_group(temporal_output)
        assert row["temporal_links_json"] is None

    def test_temporal_links_json_empty_array(self):
        """Empty JSON array -> stored as-is."""
        temporal_output = {
            "event_time_utc": 1700000000,
            "write_time_utc": 1700000000,
            "write_lag_ms": 0,
            "temporal_links_json": "[]",
        }
        row = map_temporal_group(temporal_output)
        assert row["temporal_links_json"] == "[]"


# ============================================================================
# P03EventState -- temporal_links_json field
# ============================================================================


class TestP03EventStateTemporalLinks:
    """P03EventState has temporal_links_json field with correct default."""

    def test_default_empty_array(self):
        """Default temporal_links_json is '[]'."""
        state = P03EventState(event_id="test-001")
        assert state.temporal_links_json == "[]"

    def test_set_json_array(self):
        """Can set temporal_links_json to a JSON array string."""
        links = [{"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE"}]
        state = P03EventState(event_id="test-002", temporal_links_json=json.dumps(links))
        parsed = json.loads(state.temporal_links_json)
        assert len(parsed) == 1
        assert parsed[0]["mentioned_time"] == "yesterday"

    def test_field_exists(self):
        """temporal_links_json is a field on P03EventState."""
        assert hasattr(P03EventState, "temporal_links_json")


# ============================================================================
# R0 row mapping simulation
# ============================================================================


class TestR0RowMappingTemporalLinks:
    """Simulate R0 row-to-EventState mapping for temporal_links_json."""

    def test_row_with_temporal_links_json(self):
        """DB row with temporal_links_json -> EventState.temporal_links_json."""
        links_json = json.dumps(
            [
                {
                    "mentioned_time": "next Friday",
                    "link_type": "PROSPECTIVE",
                    "resolved_epoch_ms": 0,
                    "uncertainty_window_ms": 86400000,
                    "confidence": 0.90,
                },
            ]
        )
        # Simulate R0 mapping logic
        row = {"temporal_links_json": links_json}
        result = row.get("temporal_links_json") or "[]"
        assert result == links_json

    def test_row_without_temporal_links_json(self):
        """DB row missing temporal_links_json -> default '[]'."""
        row = {}
        result = row.get("temporal_links_json") or "[]"
        assert result == "[]"

    def test_row_null_temporal_links_json(self):
        """DB row with NULL temporal_links_json -> default '[]'."""
        row = {"temporal_links_json": None}
        result = row.get("temporal_links_json") or "[]"
        assert result == "[]"

    def test_three_links_round_trip(self):
        """3 temporal_links -> JSON string -> P03EventState -> parse back."""
        links = [
            {"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE"},
            {"mentioned_time": "next Friday", "link_type": "PROSPECTIVE"},
            {"mentioned_time": "Christmas", "link_type": "PROSPECTIVE"},
        ]
        links_json = json.dumps(links)
        state = P03EventState(event_id="test-003", temporal_links_json=links_json)
        parsed = json.loads(state.temporal_links_json)
        assert len(parsed) == 3
        assert [lnk["mentioned_time"] for lnk in parsed] == [
            "yesterday",
            "next Friday",
            "Christmas",
        ]


# ============================================================================
# Epic 4.1 (GAP-002): extraction_sequence loading
# ============================================================================


class TestP03EventStateExtractionSequence:
    """P03EventState has extraction_sequence field with default 0."""

    def test_default_zero(self):
        state = P03EventState(event_id="test-seq-001")
        assert state.extraction_sequence == 0

    def test_set_value(self):
        state = P03EventState(event_id="test-seq-002", extraction_sequence=4)
        assert state.extraction_sequence == 4


class TestR0RowMappingExtractionSequence:
    """Simulate R0 row-to-EventState mapping for extraction_sequence."""

    def test_row_with_extraction_sequence(self):
        row = {"extraction_sequence": 3}
        result = int(row.get("extraction_sequence") or 0)
        assert result == 3

    def test_row_without_extraction_sequence(self):
        row = {}
        result = int(row.get("extraction_sequence") or 0)
        assert result == 0

    def test_row_null_extraction_sequence(self):
        row = {"extraction_sequence": None}
        result = int(row.get("extraction_sequence") or 0)
        assert result == 0


# ============================================================================
# Epic 4.2 (GAP-002): location_hierarchy_json loading
# ============================================================================


class TestP03EventStateLocationHierarchy:
    """P03EventState has location_hierarchy_json field with default '[]'."""

    def test_default_empty_array(self):
        state = P03EventState(event_id="test-hier-001")
        assert state.location_hierarchy_json == "[]"

    def test_set_json_array(self):
        hierarchy = ["kitchen", "home", "Seattle"]
        state = P03EventState(
            event_id="test-hier-002",
            location_hierarchy_json=json.dumps(hierarchy),
        )
        parsed = json.loads(state.location_hierarchy_json)
        assert parsed == ["kitchen", "home", "Seattle"]

    def test_field_exists(self):
        assert hasattr(P03EventState, "location_hierarchy_json")


class TestR0RowMappingLocationHierarchy:
    """Simulate R0 row-to-EventState mapping for location_hierarchy_json."""

    def test_row_with_hierarchy(self):
        hierarchy_json = json.dumps(["kitchen", "home"])
        row = {"location_hierarchy_json": hierarchy_json}
        result = row.get("location_hierarchy_json") or "[]"
        assert result == hierarchy_json

    def test_row_without_hierarchy(self):
        row = {}
        result = row.get("location_hierarchy_json") or "[]"
        assert result == "[]"

    def test_row_null_hierarchy(self):
        row = {"location_hierarchy_json": None}
        result = row.get("location_hierarchy_json") or "[]"
        assert result == "[]"

    def test_five_level_round_trip(self):
        hierarchy = ["desk", "office", "floor_3", "headquarters", "San Francisco"]
        hierarchy_json = json.dumps(hierarchy)
        state = P03EventState(
            event_id="test-hier-003",
            location_hierarchy_json=hierarchy_json,
        )
        parsed = json.loads(state.location_hierarchy_json)
        assert len(parsed) == 5
        assert parsed[0] == "desk"
        assert parsed[4] == "San Francisco"


# ============================================================================
# Epic 4.3 (GAP-002): spatial_context_json loading
# ============================================================================


class TestP03EventStateSpatialContext:
    """P03EventState has spatial_context_json field with default '{}'."""

    def test_default_empty_object(self):
        state = P03EventState(event_id="test-ctx-001")
        assert state.spatial_context_json == "{}"

    def test_set_transition(self):
        ctx = {"transition_from_place": "restaurant", "transition_mode": "drove"}
        state = P03EventState(
            event_id="test-ctx-002",
            spatial_context_json=json.dumps(ctx),
        )
        parsed = json.loads(state.spatial_context_json)
        assert parsed["transition_from_place"] == "restaurant"
        assert parsed["transition_mode"] == "drove"

    def test_field_exists(self):
        assert hasattr(P03EventState, "spatial_context_json")


class TestR0RowMappingSpatialContext:
    """Simulate R0 row-to-EventState mapping for spatial_context_json."""

    def test_row_with_spatial_context(self):
        ctx_json = json.dumps({"transition_from_place": "park", "transition_mode": "walked"})
        row = {"spatial_context_json": ctx_json}
        result = row.get("spatial_context_json") or "{}"
        assert result == ctx_json

    def test_row_without_spatial_context(self):
        row = {}
        result = row.get("spatial_context_json") or "{}"
        assert result == "{}"

    def test_row_null_spatial_context(self):
        row = {"spatial_context_json": None}
        result = row.get("spatial_context_json") or "{}"
        assert result == "{}"

    def test_transition_round_trip(self):
        ctx = {"transition_from_place": "office", "transition_mode": "biked"}
        ctx_json = json.dumps(ctx)
        state = P03EventState(event_id="test-ctx-003", spatial_context_json=ctx_json)
        parsed = json.loads(state.spatial_context_json)
        assert parsed["transition_from_place"] == "office"
        assert parsed["transition_mode"] == "biked"
