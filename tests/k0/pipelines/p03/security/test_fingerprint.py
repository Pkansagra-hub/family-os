"""Tests for content fingerprinting and deduplication."""

from __future__ import annotations

import pytest

from k0.pipelines.p03.security.fingerprint import (
    DuplicateDetector,
    deduplicate_events,
    fingerprint_event,
    fingerprint_memory,
    fingerprint_structured,
    fingerprint_text,
)


class TestFingerprintText:
    """Tests for fingerprint_text()."""

    def test_basic_fingerprint(self) -> None:
        """Create fingerprint for text."""
        fp = fingerprint_text("Hello World")
        assert fp.hash is not None
        assert len(fp.hash) == 64  # SHA-256 hex
        assert fp.content_type == "text"
        assert fp.length > 0

    def test_normalized_same_hash(self) -> None:
        """Normalized text produces same hash."""
        fp1 = fingerprint_text("Hello World")
        fp2 = fingerprint_text("  HELLO WORLD  ")
        assert fp1.hash == fp2.hash

    def test_different_content_different_hash(self) -> None:
        """Different content produces different hash."""
        fp1 = fingerprint_text("Hello")
        fp2 = fingerprint_text("World")
        assert fp1.hash != fp2.hash


class TestFingerprintStructured:
    """Tests for fingerprint_structured()."""

    def test_dict_fingerprint(self) -> None:
        """Create fingerprint for dict."""
        fp = fingerprint_structured({"a": 1, "b": 2})
        assert fp.content_type == "structured"
        assert len(fp.hash) == 64

    def test_key_order_independent(self) -> None:
        """Key order doesn't affect hash."""
        fp1 = fingerprint_structured({"a": 1, "b": 2})
        fp2 = fingerprint_structured({"b": 2, "a": 1})
        assert fp1.hash == fp2.hash


class TestFingerprintEvent:
    """Tests for fingerprint_event()."""

    def test_event_fingerprint(self) -> None:
        """Create fingerprint for event."""
        fp = fingerprint_event(
            event_type="message",
            content="Hello world",
            actor_id="user-1",
        )
        assert fp.content_type == "event"
        assert len(fp.hash) == 64

    def test_same_content_same_hash(self) -> None:
        """Same event content produces same hash."""
        fp1 = fingerprint_event("message", "Hello")
        fp2 = fingerprint_event("message", "  HELLO  ")  # Normalized
        assert fp1.hash == fp2.hash

    def test_different_type_different_hash(self) -> None:
        """Different event type produces different hash."""
        fp1 = fingerprint_event("message", "Hello")
        fp2 = fingerprint_event("notification", "Hello")
        assert fp1.hash != fp2.hash


class TestFingerprintMemory:
    """Tests for fingerprint_memory()."""

    def test_memory_fingerprint(self) -> None:
        """Create fingerprint for memory entity."""
        fp = fingerprint_memory(
            entity_type="PERSON",
            canonical_name="John Doe",
            layer="st_sem",
        )
        assert fp.content_type == "memory"
        assert len(fp.hash) == 64

    def test_normalized_name(self) -> None:
        """Canonical name is normalized."""
        fp1 = fingerprint_memory("PERSON", "John Doe", "st_sem")
        fp2 = fingerprint_memory("PERSON", "  JOHN DOE  ", "st_sem")
        assert fp1.hash == fp2.hash


class TestDuplicateDetector:
    """Tests for DuplicateDetector."""

    def test_first_is_not_duplicate(self) -> None:
        """First occurrence is not duplicate."""
        detector = DuplicateDetector()
        fp = fingerprint_text("Hello")
        assert detector.is_duplicate(fp) is False

    def test_second_is_duplicate(self) -> None:
        """Second occurrence is duplicate."""
        detector = DuplicateDetector()
        fp = fingerprint_text("Hello")
        assert detector.is_duplicate(fp) is False
        assert detector.is_duplicate(fp) is True

    def test_different_not_duplicate(self) -> None:
        """Different content is not duplicate."""
        detector = DuplicateDetector()
        fp1 = fingerprint_text("Hello")
        fp2 = fingerprint_text("World")
        assert detector.is_duplicate(fp1) is False
        assert detector.is_duplicate(fp2) is False

    def test_reset_clears(self) -> None:
        """Reset clears seen fingerprints."""
        detector = DuplicateDetector()
        fp = fingerprint_text("Hello")
        detector.is_duplicate(fp)
        assert detector.count == 1
        detector.reset()
        assert detector.count == 0
        assert detector.is_duplicate(fp) is False  # Not seen after reset


class TestDeduplicateEvents:
    """Tests for deduplicate_events()."""

    @pytest.mark.asyncio
    async def test_removes_duplicates(self) -> None:
        """Duplicate events are removed."""
        events = [
            {"event_type": "message", "content": "Hello"},
            {"event_type": "message", "content": "World"},
            {"event_type": "message", "content": "Hello"},  # Duplicate
        ]
        result = await deduplicate_events(events)
        assert len(result) == 2
        assert result[0]["content"] == "Hello"
        assert result[1]["content"] == "World"

    @pytest.mark.asyncio
    async def test_preserves_first_occurrence(self) -> None:
        """First occurrence is preserved."""
        events = [
            {"event_type": "message", "content": "Hello", "id": "first"},
            {"event_type": "message", "content": "Hello", "id": "second"},
        ]
        result = await deduplicate_events(events)
        assert len(result) == 1
        assert result[0]["id"] == "first"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        """Empty list returns empty."""
        result = await deduplicate_events([])
        assert result == []
