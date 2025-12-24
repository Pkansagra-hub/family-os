"""Unit tests for k0.db.types module."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from k0.db.types import (
    bytes_to_bytea,
    ensure_timestamp,
    ensure_uuid,
    text_to_timestamp,
    text_to_uuid,
    timestamp_now,
    timestamp_to_text,
    uuid_to_text,
)


class TestUuidConversion:
    """Tests for UUID conversion functions."""

    def test_text_to_uuid(self):
        """Convert text UUID to Python UUID."""
        text = "550e8400-e29b-41d4-a716-446655440000"
        result = text_to_uuid(text)
        assert isinstance(result, uuid.UUID)
        assert str(result) == text

    def test_text_to_uuid_none(self):
        """None returns None."""
        assert text_to_uuid(None) is None

    def test_uuid_to_text(self):
        """Convert Python UUID to text."""
        u = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        result = uuid_to_text(u)
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_uuid_to_text_none(self):
        """None returns None."""
        assert uuid_to_text(None) is None

    def test_ensure_uuid_from_string(self):
        """Ensure UUID from string."""
        text = "550e8400-e29b-41d4-a716-446655440000"
        result = ensure_uuid(text)
        assert isinstance(result, uuid.UUID)

    def test_ensure_uuid_from_uuid(self):
        """Ensure UUID from UUID (passthrough)."""
        u = uuid.uuid4()
        result = ensure_uuid(u)
        assert result is u

    def test_ensure_uuid_none(self):
        """Ensure UUID from None."""
        assert ensure_uuid(None) is None


class TestTimestampConversion:
    """Tests for timestamp conversion functions."""

    def test_text_to_timestamp_z_suffix(self):
        """Convert ISO8601 with Z suffix."""
        text = "2024-01-15T10:30:00.000000Z"
        result = text_to_timestamp(text)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_text_to_timestamp_offset(self):
        """Convert ISO8601 with +00:00."""
        text = "2024-01-15T10:30:00+00:00"
        result = text_to_timestamp(text)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_text_to_timestamp_datetime(self):
        """Datetime passthrough adds UTC if naive."""
        dt = datetime(2024, 1, 15)
        result = text_to_timestamp(dt)
        assert result.tzinfo == timezone.utc

    def test_text_to_timestamp_datetime_aware(self):
        """Aware datetime passes through."""
        dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = text_to_timestamp(dt)
        assert result is dt

    def test_text_to_timestamp_none(self):
        """None returns None."""
        assert text_to_timestamp(None) is None

    def test_timestamp_to_text(self):
        """Convert datetime to ISO8601 text."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = timestamp_to_text(dt)
        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_timestamp_to_text_naive(self):
        """Naive datetime gets UTC."""
        dt = datetime(2024, 1, 15)
        result = timestamp_to_text(dt)
        assert "+00:00" in result

    def test_timestamp_to_text_none(self):
        """None returns None."""
        assert timestamp_to_text(None) is None

    def test_timestamp_now(self):
        """Get current UTC timestamp."""
        result = timestamp_now()
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_ensure_timestamp_string(self):
        """Ensure timestamp from string."""
        result = ensure_timestamp("2024-01-15T10:30:00Z")
        assert isinstance(result, datetime)

    def test_ensure_timestamp_datetime(self):
        """Ensure timestamp from datetime."""
        dt = datetime(2024, 1, 15)
        result = ensure_timestamp(dt)
        assert result.tzinfo == timezone.utc


class TestBytesConversion:
    """Tests for bytes/BYTEA conversion."""

    def test_bytes_to_bytea(self):
        """Bytes passthrough."""
        b = b"binary data"
        result = bytes_to_bytea(b)
        assert result is b

    def test_bytes_to_bytea_none(self):
        """None returns None."""
        assert bytes_to_bytea(None) is None
