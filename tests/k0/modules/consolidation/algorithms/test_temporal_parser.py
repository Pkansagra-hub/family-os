"""
Unit tests for TemporalParser.

Tests parsing of UltraBERT temporal_json format to Unix timestamps.
Covers relative dates, absolute times, combined expressions.
"""

import json
from datetime import datetime

import pytest

from k0.modules.consolidation.algorithms.temporal_parser import (
    ParseResult,
    TemporalParser,
    create_temporal_parser,
    parse_temporal_expression,
)


class TestTemporalParserRelativeDates:
    """Test relative date parsing (tomorrow, next week, etc.)."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        """Create parser instance."""
        return TemporalParser()

    @pytest.fixture
    def ref_time_ms(self) -> int:
        """Fixed reference time: 2025-01-15 10:00:00 (Wednesday)."""
        return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)

    def test_parse_tomorrow(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'tomorrow'."""
        temporal_json = json.dumps({"entities": [{"text": "tomorrow", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 16)
        assert result_dt.date() == expected.date()

    def test_parse_today(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'today'."""
        temporal_json = json.dumps({"entities": [{"text": "today", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.date() == datetime(2025, 1, 15).date()

    def test_parse_next_week(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'next week'."""
        temporal_json = json.dumps({"entities": [{"text": "next week", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 22).date()  # +7 days
        assert result_dt.date() == expected

    def test_parse_next_monday(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'next Monday' from Wednesday."""
        temporal_json = json.dumps({"entities": [{"text": "next Monday", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        # From Wednesday (day 2), next Monday (day 0) is +5 days
        assert result_dt.weekday() == 0  # Monday

    def test_parse_next_friday(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'next Friday' from Wednesday."""
        temporal_json = json.dumps({"entities": [{"text": "next Friday", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.weekday() == 4  # Friday


class TestTemporalParserRelativeTime:
    """Test relative time parsing (in an hour, in 30 minutes)."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        return TemporalParser()

    @pytest.fixture
    def ref_time_ms(self) -> int:
        return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)

    def test_parse_in_an_hour(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'in an hour'."""
        temporal_json = json.dumps({"entities": [{"text": "in an hour", "label": "TIME_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 15, 11, 0, 0)
        assert result_dt.hour == expected.hour

    def test_parse_in_30_minutes(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'in 30 minutes'."""
        temporal_json = json.dumps({"entities": [{"text": "in 30 minutes", "label": "TIME_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 15, 10, 30, 0)
        assert result_dt.minute == expected.minute

    def test_parse_in_2_hours(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'in 2 hours'."""
        temporal_json = json.dumps({"entities": [{"text": "in 2 hours", "label": "TIME_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 15, 12, 0, 0)
        assert result_dt.hour == expected.hour

    def test_parse_in_half_an_hour(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'in half an hour'."""
        temporal_json = json.dumps({"entities": [{"text": "in half an hour", "label": "TIME_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 15, 10, 30, 0)
        assert result_dt.minute == expected.minute

    def test_parse_in_3_days(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'in 3 days'."""
        temporal_json = json.dumps({"entities": [{"text": "in 3 days", "label": "TIME_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        expected = datetime(2025, 1, 18).date()
        assert result_dt.date() == expected


class TestTemporalParserAbsoluteTime:
    """Test absolute time parsing (3pm, 15:00)."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        return TemporalParser()

    @pytest.fixture
    def ref_time_ms(self) -> int:
        return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)

    def test_parse_3pm(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing '3pm'."""
        temporal_json = json.dumps({"entities": [{"text": "3pm", "label": "TIME"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 15
        assert result_dt.minute == 0

    def test_parse_3_30_pm(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing '3:30 PM'."""
        temporal_json = json.dumps({"entities": [{"text": "3:30 PM", "label": "TIME"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 15
        assert result_dt.minute == 30

    def test_parse_15_00(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing '15:00' (24-hour format)."""
        temporal_json = json.dumps({"entities": [{"text": "15:00", "label": "TIME"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 15
        assert result_dt.minute == 0

    def test_parse_10am(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing '10am'."""
        temporal_json = json.dumps({"entities": [{"text": "10am", "label": "TIME"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 10

    def test_parse_12pm_noon(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing '12pm' (noon)."""
        temporal_json = json.dumps({"entities": [{"text": "12pm", "label": "TIME"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 12


class TestTemporalParserCombined:
    """Test combined date+time expressions."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        return TemporalParser()

    @pytest.fixture
    def ref_time_ms(self) -> int:
        return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)

    def test_parse_tomorrow_at_3pm(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'tomorrow at 3pm'."""
        temporal_json = json.dumps({"entities": [{"text": "tomorrow at 3pm", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.date() == datetime(2025, 1, 16).date()
        assert result_dt.hour == 15
        assert result_dt.minute == 0

    def test_parse_next_monday_at_10am(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'next Monday at 10am'."""
        temporal_json = json.dumps(
            {"entities": [{"text": "next Monday at 10am", "label": "DATE_REL"}]}
        )
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.weekday() == 0  # Monday
        assert result_dt.hour == 10

    def test_parse_today_at_5_30_pm(self, parser: TemporalParser, ref_time_ms: int):
        """Test parsing 'today at 5:30 pm'."""
        temporal_json = json.dumps(
            {"entities": [{"text": "today at 5:30 pm", "label": "DATE_REL"}]}
        )
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.date() == datetime(2025, 1, 15).date()
        assert result_dt.hour == 17
        assert result_dt.minute == 30


class TestTemporalParserEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        return TemporalParser()

    def test_empty_json(self, parser: TemporalParser):
        """Test empty JSON string."""
        result = parser.parse_temporal_json("")
        assert result is None

    def test_invalid_json(self, parser: TemporalParser):
        """Test invalid JSON string."""
        result = parser.parse_temporal_json("not json")
        assert result is None

    def test_no_entities(self, parser: TemporalParser):
        """Test JSON with no entities."""
        temporal_json = json.dumps({"entities": []})
        result = parser.parse_temporal_json(temporal_json)
        assert result is None

    def test_non_temporal_entity(self, parser: TemporalParser):
        """Test entity with non-temporal label."""
        temporal_json = json.dumps({"entities": [{"text": "John", "label": "PERSON"}]})
        result = parser.parse_temporal_json(temporal_json)
        assert result is None

    def test_unparseable_time(self, parser: TemporalParser):
        """Test unparseable temporal text."""
        temporal_json = json.dumps({"entities": [{"text": "sometime later", "label": "TIME"}]})
        result = parser.parse_temporal_json(temporal_json)
        # "sometime later" has no specific time pattern
        assert result is None

    def test_first_parseable_entity(self, parser: TemporalParser):
        """Test that first parseable entity is used."""
        temporal_json = json.dumps(
            {
                "entities": [
                    {"text": "unknown", "label": "TIME"},
                    {"text": "3pm", "label": "TIME"},
                ]
            }
        )
        ref_time_ms = int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 15


class TestTemporalParserFull:
    """Test parse_temporal_json_full with detailed results."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        return TemporalParser()

    @pytest.fixture
    def ref_time_ms(self) -> int:
        return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)

    def test_full_parse_success(self, parser: TemporalParser, ref_time_ms: int):
        """Test full parse with successful result."""
        temporal_json = json.dumps({"entities": [{"text": "tomorrow at 3pm", "label": "DATE_REL"}]})
        result = parser.parse_temporal_json_full(temporal_json, ref_time_ms)

        assert isinstance(result, ParseResult)
        assert result.timestamp_ms is not None
        assert result.entity is not None
        assert result.entity.text == "tomorrow at 3pm"
        assert result.entity.label == "DATE_REL"
        assert result.confidence > 0.8
        assert result.parse_method == "pattern_match"

    def test_full_parse_empty(self, parser: TemporalParser):
        """Test full parse with empty input."""
        result = parser.parse_temporal_json_full("")

        assert result.timestamp_ms is None
        assert result.entity is None
        assert result.confidence == 0.0
        assert result.parse_method == "none"

    def test_full_parse_invalid_json(self, parser: TemporalParser):
        """Test full parse with invalid JSON."""
        result = parser.parse_temporal_json_full("not json")

        assert result.timestamp_ms is None
        assert result.parse_method == "json_error"

    def test_full_parse_no_entities(self, parser: TemporalParser):
        """Test full parse with no entities."""
        result = parser.parse_temporal_json_full(json.dumps({"entities": []}))

        assert result.timestamp_ms is None
        assert result.parse_method == "no_entities"

    def test_full_parse_no_match(self, parser: TemporalParser):
        """Test full parse with unparseable entity."""
        temporal_json = json.dumps({"entities": [{"text": "sometime", "label": "TIME"}]})
        result = parser.parse_temporal_json_full(temporal_json)

        assert result.timestamp_ms is None
        assert result.parse_method == "no_match"


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_create_temporal_parser(self):
        """Test factory function."""
        parser = create_temporal_parser()
        assert isinstance(parser, TemporalParser)

    def test_parse_temporal_expression(self):
        """Test convenience parse function."""
        temporal_json = json.dumps({"entities": [{"text": "3pm", "label": "TIME"}]})
        ref_time_ms = int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)
        result = parse_temporal_expression(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 15


class TestTemporalParserIntegration:
    """Integration tests with realistic UltraBERT output formats."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        return TemporalParser()

    @pytest.fixture
    def ref_time_ms(self) -> int:
        return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)

    def test_ultrabert_reminder_format(self, parser: TemporalParser, ref_time_ms: int):
        """Test UltraBERT output for reminder scenario."""
        # "Remind me tomorrow at 3pm to call mom"
        temporal_json = json.dumps(
            {
                "entities": [
                    {"text": "tomorrow at 3pm", "label": "DATE_REL", "start": 11, "end": 26},
                ]
            }
        )
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.date() == datetime(2025, 1, 16).date()
        assert result_dt.hour == 15

    def test_ultrabert_meeting_format(self, parser: TemporalParser, ref_time_ms: int):
        """Test UltraBERT output for meeting scenario."""
        # "Schedule a meeting next Monday at 10am"
        temporal_json = json.dumps(
            {
                "entities": [
                    {"text": "next Monday at 10am", "label": "DATE_REL", "start": 20, "end": 39},
                ]
            }
        )
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.weekday() == 0
        assert result_dt.hour == 10

    def test_ultrabert_appointment_format(self, parser: TemporalParser, ref_time_ms: int):
        """Test UltraBERT output for appointment scenario."""
        # "I have a doctor's appointment in 2 hours"
        temporal_json = json.dumps(
            {
                "entities": [
                    {"text": "in 2 hours", "label": "TIME_REL", "start": 33, "end": 43},
                ]
            }
        )
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.hour == 12

    def test_multiple_temporal_entities(self, parser: TemporalParser, ref_time_ms: int):
        """Test when multiple temporal entities exist."""
        # "Tomorrow at 3pm, but not before next week"
        temporal_json = json.dumps(
            {
                "entities": [
                    {"text": "Tomorrow at 3pm", "label": "DATE_REL", "start": 0, "end": 15},
                    {"text": "next week", "label": "DATE_REL", "start": 33, "end": 42},
                ]
            }
        )
        result = parser.parse_temporal_json(temporal_json, ref_time_ms)

        # Should use first parseable entity
        assert result is not None
        result_dt = datetime.fromtimestamp(result / 1000)
        assert result_dt.date() == datetime(2025, 1, 16).date()
        assert result_dt.hour == 15
