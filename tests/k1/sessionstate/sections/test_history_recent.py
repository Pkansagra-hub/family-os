"""
Tests for HistoryRecentSection.

Issue: 2.3.2 (WARM tier - history_recent)
Budget: 20KB (20480 bytes)
Eviction Priority: 3

Tests cover:
- CompressedTurn dataclass
- SummarizedTurn dataclass
- ISection protocol compliance
- IEvictable protocol compliance
- Compressed turns API
- Summarized turns API
- Compression pipeline
- Session summary API
- Query API
- Archive management
- FlatBuffer serialization
- Apply operations
- Edge cases
"""

import time

import pytest

from k1.sessionstate.sections.history_recent import (
    CompressedTurn,
    EvictedData,
    HistoryRecentSection,
    SummarizedTurn,
    create_history_recent_section,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> HistoryRecentSection:
    """Create fresh HistoryRecentSection."""
    return HistoryRecentSection()


@pytest.fixture
def sample_compressed_turn() -> CompressedTurn:
    """Create sample compressed turn."""
    return CompressedTurn(
        turn_id="turn-001",
        turn_number=11,
        entities=["Alice", "Project-X"],
        intents=["schedule_meeting"],
        key_phrases=["meeting tomorrow", "9am"],
        timestamp_ms=1700000000000,
        emotion="neutral",
        user_tokens=50,
        response_tokens=75,
    )


@pytest.fixture
def sample_summarized_turn() -> SummarizedTurn:
    """Create sample summarized turn."""
    return SummarizedTurn(
        turn_id="turn-031",
        turn_number=31,
        summary="User scheduled meeting with Alice for Project-X",
        timestamp_ms=1700000000000,
        primary_intent="schedule_meeting",
        primary_entity="Alice",
    )


@pytest.fixture
def populated_section(section: HistoryRecentSection) -> HistoryRecentSection:
    """Create section with compressed and summarized turns."""
    # Add 5 compressed turns
    for i in range(5):
        turn = CompressedTurn(
            turn_id=f"turn-{11 + i:03d}",
            turn_number=11 + i,
            entities=[f"Entity-{i}"],
            intents=[f"intent_{i}"],
            key_phrases=[f"phrase-{i}"],
            timestamp_ms=1700000000000 + (i * 1000),
        )
        section.add_compressed_turn(turn)

    # Add 3 summarized turns
    for i in range(3):
        turn = SummarizedTurn(
            turn_id=f"turn-{31 + i:03d}",
            turn_number=31 + i,
            summary=f"Summary for turn {31 + i}",
            timestamp_ms=1700000000000 + (i * 1000),
        )
        section.add_summarized_turn(turn)

    section.set_session_summary("Test session summary")
    return section


# =============================================================================
# CompressedTurn Dataclass Tests
# =============================================================================


class TestCompressedTurn:
    """Tests for CompressedTurn dataclass."""

    def test_create_empty(self) -> None:
        """Test creating empty compressed turn."""
        turn = CompressedTurn(turn_id="t1", turn_number=11)

        assert turn.turn_id == "t1"
        assert turn.turn_number == 11
        assert turn.entities == []
        assert turn.intents == []
        assert turn.key_phrases == []
        assert turn.timestamp_ms == 0
        assert turn.emotion == ""
        assert turn.user_tokens == 0
        assert turn.response_tokens == 0
        assert turn.archived_to_local_cold is False
        assert turn.archive_id == ""

    def test_create_with_data(self, sample_compressed_turn: CompressedTurn) -> None:
        """Test creating compressed turn with data."""
        assert sample_compressed_turn.turn_id == "turn-001"
        assert sample_compressed_turn.turn_number == 11
        assert sample_compressed_turn.entities == ["Alice", "Project-X"]
        assert sample_compressed_turn.intents == ["schedule_meeting"]
        assert sample_compressed_turn.key_phrases == ["meeting tomorrow", "9am"]
        assert sample_compressed_turn.emotion == "neutral"
        assert sample_compressed_turn.user_tokens == 50
        assert sample_compressed_turn.response_tokens == 75

    def test_to_dict(self, sample_compressed_turn: CompressedTurn) -> None:
        """Test converting to dictionary."""
        d = sample_compressed_turn.to_dict()

        assert d["turn_id"] == "turn-001"
        assert d["turn_number"] == 11
        assert d["entities"] == ["Alice", "Project-X"]
        assert d["intents"] == ["schedule_meeting"]
        assert d["key_phrases"] == ["meeting tomorrow", "9am"]
        assert d["archived_to_local_cold"] is False

    def test_from_full_turn(self) -> None:
        """Test factory method from full turn data."""
        turn = CompressedTurn.from_full_turn(
            turn_id="t1",
            turn_number=15,
            entities=["Bob"],
            intents=["ask_question"],
            key_phrases=["how to", "debug"],
            timestamp_ms=1234567890,
            emotion="confused",
            user_tokens=30,
            response_tokens=100,
        )

        assert turn.turn_id == "t1"
        assert turn.turn_number == 15
        assert turn.entities == ["Bob"]
        assert turn.intents == ["ask_question"]
        assert turn.key_phrases == ["how to", "debug"]
        assert turn.emotion == "confused"

    def test_archive_tracking(self) -> None:
        """Test archive tracking fields."""
        turn = CompressedTurn(
            turn_id="t1",
            turn_number=11,
            archived_to_local_cold=True,
            archive_id="arch-001",
        )

        assert turn.archived_to_local_cold is True
        assert turn.archive_id == "arch-001"


# =============================================================================
# SummarizedTurn Dataclass Tests
# =============================================================================


class TestSummarizedTurn:
    """Tests for SummarizedTurn dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating minimal summarized turn."""
        turn = SummarizedTurn(
            turn_id="t31",
            turn_number=31,
            summary="User asked about scheduling",
        )

        assert turn.turn_id == "t31"
        assert turn.turn_number == 31
        assert turn.summary == "User asked about scheduling"
        assert turn.timestamp_ms == 0
        assert turn.primary_intent == ""
        assert turn.primary_entity == ""
        assert turn.archived_to_local_cold is False

    def test_create_with_data(self, sample_summarized_turn: SummarizedTurn) -> None:
        """Test creating summarized turn with full data."""
        assert sample_summarized_turn.turn_id == "turn-031"
        assert sample_summarized_turn.turn_number == 31
        assert sample_summarized_turn.summary == "User scheduled meeting with Alice for Project-X"
        assert sample_summarized_turn.primary_intent == "schedule_meeting"
        assert sample_summarized_turn.primary_entity == "Alice"

    def test_to_dict(self, sample_summarized_turn: SummarizedTurn) -> None:
        """Test converting to dictionary."""
        d = sample_summarized_turn.to_dict()

        assert d["turn_id"] == "turn-031"
        assert d["turn_number"] == 31
        assert d["summary"] == "User scheduled meeting with Alice for Project-X"
        assert d["primary_intent"] == "schedule_meeting"
        assert d["primary_entity"] == "Alice"

    def test_from_compressed(self, sample_compressed_turn: CompressedTurn) -> None:
        """Test creating from compressed turn."""
        summarized = SummarizedTurn.from_compressed(
            sample_compressed_turn,
            summary="Meeting scheduled with Alice",
        )

        assert summarized.turn_id == sample_compressed_turn.turn_id
        assert summarized.turn_number == sample_compressed_turn.turn_number
        assert summarized.summary == "Meeting scheduled with Alice"
        assert summarized.timestamp_ms == sample_compressed_turn.timestamp_ms
        assert summarized.primary_intent == "schedule_meeting"
        assert summarized.primary_entity == "Alice"

    def test_from_compressed_empty_arrays(self) -> None:
        """Test creating from compressed with empty entities/intents."""
        compressed = CompressedTurn(
            turn_id="t1",
            turn_number=11,
            entities=[],
            intents=[],
        )
        summarized = SummarizedTurn.from_compressed(compressed, summary="Empty turn")

        assert summarized.primary_intent == ""
        assert summarized.primary_entity == ""


# =============================================================================
# ISection Protocol Tests
# =============================================================================


class TestISection:
    """Tests for ISection protocol compliance."""

    def test_name(self, section: HistoryRecentSection) -> None:
        """Test section name."""
        assert section.name == "history_recent"

    def test_tier(self, section: HistoryRecentSection) -> None:
        """Test section tier."""
        assert section.tier == "warm"

    def test_budget_bytes(self, section: HistoryRecentSection) -> None:
        """Test budget bytes."""
        assert section.budget_bytes == 20480  # 20KB

    def test_get_size_bytes_empty(self, section: HistoryRecentSection) -> None:
        """Test size of empty section."""
        size = section.get_size_bytes()
        # Base size ~500 bytes
        assert 400 <= size <= 600

    def test_get_size_bytes_with_data(self, populated_section: HistoryRecentSection) -> None:
        """Test size with data."""
        size = populated_section.get_size_bytes()
        # 5 compressed * 700 + 3 summarized * 200 + base + summary
        # = 3500 + 600 + 500 + 20 ~ 4600
        assert size > 4000
        assert size < 10000

    def test_clear(self, populated_section: HistoryRecentSection) -> None:
        """Test clearing section."""
        populated_section.clear()

        assert populated_section.compressed_count() == 0
        assert populated_section.summarized_count() == 0
        assert populated_section.get_session_summary() == ""
        assert populated_section.get_total_turns_archived() == 0

    def test_to_dict(self, populated_section: HistoryRecentSection) -> None:
        """Test to_dict conversion."""
        d = populated_section.to_dict()

        assert d["name"] == "history_recent"
        assert d["tier"] == "warm"
        assert d["size_bytes"] > 0
        assert d["budget_bytes"] == 20480
        assert len(d["compressed_turns"]) == 5
        assert len(d["summarized_turns"]) == 3
        assert d["session_summary"] == "Test session summary"


# =============================================================================
# IEvictable Protocol Tests
# =============================================================================


class TestIEvictable:
    """Tests for IEvictable protocol compliance."""

    def test_get_eviction_priority(self, section: HistoryRecentSection) -> None:
        """Test eviction priority."""
        assert section.get_eviction_priority() == 3

    def test_can_evict_empty(self, section: HistoryRecentSection) -> None:
        """Test empty section cannot evict."""
        assert section.can_evict() is False

    def test_can_evict_with_compressed(self, section: HistoryRecentSection) -> None:
        """Test section with compressed turns can evict."""
        section.add_compressed_turn(CompressedTurn(turn_id="t1", turn_number=11))
        assert section.can_evict() is True

    def test_can_evict_with_summarized(self, section: HistoryRecentSection) -> None:
        """Test section with summarized turns can evict."""
        section.add_summarized_turn(SummarizedTurn(turn_id="t31", turn_number=31, summary="s"))
        assert section.can_evict() is True

    def test_evict_partial_summarized_first(self, populated_section: HistoryRecentSection) -> None:
        """Test eviction evicts summarized turns first."""
        initial_summarized = populated_section.summarized_count()
        initial_compressed = populated_section.compressed_count()

        evicted = populated_section.evict_partial(target_kb=0.5)

        # Should evict summarized first
        assert len(evicted.summarized_turns) > 0
        assert populated_section.summarized_count() < initial_summarized
        # Compressed should be untouched if enough summarized evicted
        if evicted.bytes_freed >= 512:
            assert populated_section.compressed_count() == initial_compressed

    def test_evict_partial_compressed_after_summarized(self, section: HistoryRecentSection) -> None:
        """Test eviction evicts compressed after summarized exhausted."""
        # Add only compressed turns
        for i in range(5):
            section.add_compressed_turn(CompressedTurn(turn_id=f"t{11+i}", turn_number=11 + i))

        evicted = section.evict_partial(target_kb=2)

        assert len(evicted.compressed_turns) > 0
        assert len(evicted.summarized_turns) == 0

    def test_evict_tracks_bytes(self, populated_section: HistoryRecentSection) -> None:
        """Test eviction tracks bytes freed."""
        evicted = populated_section.evict_partial(target_kb=1)

        assert evicted.bytes_freed > 0
        assert populated_section.get_bytes_evicted_total() == evicted.bytes_freed

    def test_evict_tracks_timestamp(self, populated_section: HistoryRecentSection) -> None:
        """Test eviction updates timestamp."""
        before = int(time.time() * 1000) - 1

        populated_section.evict_partial(target_kb=0.5)

        assert populated_section.get_last_eviction_ms() >= before

    def test_evict_tracks_archived_ids(self, populated_section: HistoryRecentSection) -> None:
        """Test eviction tracks archived turn IDs."""
        evicted = populated_section.evict_partial(target_kb=0.5)

        archived_ids = populated_section.get_archived_turn_ids()
        evicted_ids = [t.turn_id for t in evicted.summarized_turns] + [
            t.turn_id for t in evicted.compressed_turns
        ]

        for tid in evicted_ids:
            assert tid in archived_ids

    def test_evicted_data_structure(self, populated_section: HistoryRecentSection) -> None:
        """Test EvictedData structure."""
        evicted = populated_section.evict_partial(target_kb=1)

        assert isinstance(evicted, EvictedData)
        assert isinstance(evicted.compressed_turns, list)
        assert isinstance(evicted.summarized_turns, list)
        assert isinstance(evicted.bytes_freed, int)
        assert evicted.eviction_reason == "pressure"


# =============================================================================
# Compressed Turns API Tests
# =============================================================================


class TestCompressedTurnsAPI:
    """Tests for compressed turns API."""

    def test_add_compressed_turn(
        self, section: HistoryRecentSection, sample_compressed_turn: CompressedTurn
    ) -> None:
        """Test adding compressed turn."""
        result = section.add_compressed_turn(sample_compressed_turn)

        assert result is True
        assert section.compressed_count() == 1

    def test_add_compressed_turns(self, section: HistoryRecentSection) -> None:
        """Test adding multiple compressed turns."""
        turns = [CompressedTurn(turn_id=f"t{i}", turn_number=11 + i) for i in range(5)]

        count = section.add_compressed_turns(turns)

        assert count == 5
        assert section.compressed_count() == 5

    def test_add_compressed_maintains_order(self, section: HistoryRecentSection) -> None:
        """Test turns are ordered by turn_number."""
        section.add_compressed_turn(CompressedTurn(turn_id="t2", turn_number=15))
        section.add_compressed_turn(CompressedTurn(turn_id="t1", turn_number=11))
        section.add_compressed_turn(CompressedTurn(turn_id="t3", turn_number=13))

        turns = section.list_compressed_turns()
        numbers = [t.turn_number for t in turns]

        assert numbers == [11, 13, 15]

    def test_get_compressed_turn(
        self, section: HistoryRecentSection, sample_compressed_turn: CompressedTurn
    ) -> None:
        """Test getting compressed turn by ID."""
        section.add_compressed_turn(sample_compressed_turn)

        found = section.get_compressed_turn("turn-001")

        assert found is not None
        assert found.turn_id == "turn-001"

    def test_get_compressed_not_found(self, section: HistoryRecentSection) -> None:
        """Test getting non-existent compressed turn."""
        assert section.get_compressed_turn("nonexistent") is None

    def test_get_compressed_by_number(
        self, section: HistoryRecentSection, sample_compressed_turn: CompressedTurn
    ) -> None:
        """Test getting compressed turn by number."""
        section.add_compressed_turn(sample_compressed_turn)

        found = section.get_compressed_by_number(11)

        assert found is not None
        assert found.turn_number == 11

    def test_list_compressed_turns(self, populated_section: HistoryRecentSection) -> None:
        """Test listing compressed turns."""
        turns = populated_section.list_compressed_turns()

        assert len(turns) == 5
        # Should be in order
        for i, turn in enumerate(turns):
            assert turn.turn_number == 11 + i

    def test_compressed_count(self, populated_section: HistoryRecentSection) -> None:
        """Test compressed count."""
        assert populated_section.compressed_count() == 5

    def test_oldest_newest_compressed(self, populated_section: HistoryRecentSection) -> None:
        """Test oldest/newest compressed turn tracking."""
        assert populated_section.get_oldest_compressed_turn() == 11
        assert populated_section.get_newest_compressed_turn() == 15

    def test_oldest_newest_empty(self, section: HistoryRecentSection) -> None:
        """Test oldest/newest with no turns."""
        assert section.get_oldest_compressed_turn() == 0
        assert section.get_newest_compressed_turn() == 0

    def test_capacity_triggers_compression(self, section: HistoryRecentSection) -> None:
        """Test adding beyond capacity triggers compression."""
        # Fill to capacity
        for i in range(section.MAX_COMPRESSED_TURNS):
            section.add_compressed_turn(CompressedTurn(turn_id=f"t{i}", turn_number=11 + i))

        initial_summarized = section.summarized_count()

        # Add one more
        section.add_compressed_turn(CompressedTurn(turn_id="overflow", turn_number=100))

        # Should have compressed oldest to summarized
        assert section.summarized_count() > initial_summarized
        assert section.compressed_count() == section.MAX_COMPRESSED_TURNS


# =============================================================================
# Summarized Turns API Tests
# =============================================================================


class TestSummarizedTurnsAPI:
    """Tests for summarized turns API."""

    def test_add_summarized_turn(
        self, section: HistoryRecentSection, sample_summarized_turn: SummarizedTurn
    ) -> None:
        """Test adding summarized turn."""
        result = section.add_summarized_turn(sample_summarized_turn)

        assert result is True
        assert section.summarized_count() == 1

    def test_add_summarized_maintains_order(self, section: HistoryRecentSection) -> None:
        """Test summarized turns ordered by turn_number."""
        section.add_summarized_turn(SummarizedTurn(turn_id="t33", turn_number=33, summary="s3"))
        section.add_summarized_turn(SummarizedTurn(turn_id="t31", turn_number=31, summary="s1"))
        section.add_summarized_turn(SummarizedTurn(turn_id="t32", turn_number=32, summary="s2"))

        turns = section.list_summarized_turns()
        numbers = [t.turn_number for t in turns]

        assert numbers == [31, 32, 33]

    def test_get_summarized_turn(
        self, section: HistoryRecentSection, sample_summarized_turn: SummarizedTurn
    ) -> None:
        """Test getting summarized turn by ID."""
        section.add_summarized_turn(sample_summarized_turn)

        found = section.get_summarized_turn("turn-031")

        assert found is not None
        assert found.turn_id == "turn-031"

    def test_get_summarized_by_number(
        self, section: HistoryRecentSection, sample_summarized_turn: SummarizedTurn
    ) -> None:
        """Test getting summarized turn by number."""
        section.add_summarized_turn(sample_summarized_turn)

        found = section.get_summarized_by_number(31)

        assert found is not None
        assert found.turn_number == 31

    def test_list_summarized_turns(self, populated_section: HistoryRecentSection) -> None:
        """Test listing summarized turns."""
        turns = populated_section.list_summarized_turns()

        assert len(turns) == 3
        for i, turn in enumerate(turns):
            assert turn.turn_number == 31 + i

    def test_oldest_newest_summarized(self, populated_section: HistoryRecentSection) -> None:
        """Test oldest/newest summarized turn tracking."""
        assert populated_section.get_oldest_summarized_turn() == 31
        assert populated_section.get_newest_summarized_turn() == 33

    def test_capacity_triggers_eviction(self, section: HistoryRecentSection) -> None:
        """Test adding beyond capacity triggers eviction."""
        # Fill to capacity
        for i in range(section.MAX_SUMMARIZED_TURNS):
            section.add_summarized_turn(
                SummarizedTurn(turn_id=f"t{31+i}", turn_number=31 + i, summary=f"s{i}")
            )

        initial_archived = section.get_total_turns_archived()

        # Add one more
        section.add_summarized_turn(
            SummarizedTurn(turn_id="overflow", turn_number=100, summary="overflow")
        )

        # Should have evicted oldest
        assert section.get_total_turns_archived() > initial_archived
        assert section.summarized_count() == section.MAX_SUMMARIZED_TURNS


# =============================================================================
# Compression Pipeline Tests
# =============================================================================


class TestCompressionPipeline:
    """Tests for compression pipeline."""

    def test_compress_to_summarized(self, section: HistoryRecentSection) -> None:
        """Test compressing oldest compressed to summarized."""
        section.add_compressed_turn(
            CompressedTurn(
                turn_id="t1",
                turn_number=11,
                entities=["Alice"],
                intents=["schedule"],
                key_phrases=["meeting"],
            )
        )

        summarized = section.compress_to_summarized(count=1)

        assert len(summarized) == 1
        assert section.compressed_count() == 0
        assert section.summarized_count() == 1

    def test_compress_to_summarized_default_summary(self, section: HistoryRecentSection) -> None:
        """Test default summary generation."""
        section.add_compressed_turn(
            CompressedTurn(
                turn_id="t1",
                turn_number=11,
                entities=["Alice", "Bob"],
                intents=["schedule"],
                emotion="happy",
            )
        )

        summarized = section.compress_to_summarized(count=1)

        # Default summary includes intent, entities, emotion
        summary = summarized[0].summary
        assert "schedule" in summary.lower() or "Intent:" in summary
        assert summarized[0].primary_intent == "schedule"
        assert summarized[0].primary_entity == "Alice"

    def test_compress_with_custom_generator(self, section: HistoryRecentSection) -> None:
        """Test compression with custom summary generator."""
        section.add_compressed_turn(
            CompressedTurn(turn_id="t1", turn_number=11, entities=["Alice"])
        )

        def custom_gen(turn: CompressedTurn) -> str:
            return f"Custom summary for turn {turn.turn_number}"

        summarized = section.compress_to_summarized(count=1, summary_generator=custom_gen)

        assert summarized[0].summary == "Custom summary for turn 11"

    def test_compress_multiple(self, section: HistoryRecentSection) -> None:
        """Test compressing multiple turns."""
        for i in range(5):
            section.add_compressed_turn(CompressedTurn(turn_id=f"t{i}", turn_number=11 + i))

        summarized = section.compress_to_summarized(count=3)

        assert len(summarized) == 3
        assert section.compressed_count() == 2
        assert section.summarized_count() == 3

    def test_compress_empty(self, section: HistoryRecentSection) -> None:
        """Test compressing empty section."""
        summarized = section.compress_to_summarized(count=1)

        assert len(summarized) == 0


# =============================================================================
# Session Summary API Tests
# =============================================================================


class TestSessionSummaryAPI:
    """Tests for session summary API."""

    def test_set_session_summary(self, section: HistoryRecentSection) -> None:
        """Test setting session summary."""
        section.set_session_summary("This is a test session")

        assert section.get_session_summary() == "This is a test session"

    def test_set_session_summary_truncates(self, section: HistoryRecentSection) -> None:
        """Test session summary truncated to max length."""
        long_summary = "x" * 300

        section.set_session_summary(long_summary)

        assert len(section.get_session_summary()) == 200

    def test_update_session_summary(self, section: HistoryRecentSection) -> None:
        """Test updating session summary."""
        section.set_session_summary("Initial summary")

        result = section.update_session_summary("Added context")

        assert "Initial summary" in result
        assert "Added context" in result

    def test_update_empty_summary(self, section: HistoryRecentSection) -> None:
        """Test updating empty summary."""
        result = section.update_session_summary("First context")

        assert result == "First context"


# =============================================================================
# Query API Tests
# =============================================================================


class TestQueryAPI:
    """Tests for query API."""

    def test_get_turn_compressed(self, populated_section: HistoryRecentSection) -> None:
        """Test getting turn from compressed."""
        turn = populated_section.get_turn("turn-011")

        assert turn is not None
        assert turn.turn_id == "turn-011"
        assert isinstance(turn, CompressedTurn)

    def test_get_turn_summarized(self, populated_section: HistoryRecentSection) -> None:
        """Test getting turn from summarized."""
        turn = populated_section.get_turn("turn-031")

        assert turn is not None
        assert turn.turn_id == "turn-031"
        assert isinstance(turn, SummarizedTurn)

    def test_get_turn_not_found(self, populated_section: HistoryRecentSection) -> None:
        """Test getting non-existent turn."""
        assert populated_section.get_turn("nonexistent") is None

    def test_get_by_number(self, populated_section: HistoryRecentSection) -> None:
        """Test getting turn by number."""
        turn = populated_section.get_by_number(12)

        assert turn is not None
        assert turn.turn_number == 12

    def test_get_turns_by_entity(self, populated_section: HistoryRecentSection) -> None:
        """Test getting turns by entity."""
        turns = populated_section.get_turns_by_entity("Entity-1")

        assert len(turns) == 1
        assert "Entity-1" in turns[0].entities

    def test_get_turns_by_intent(self, populated_section: HistoryRecentSection) -> None:
        """Test getting turns by intent."""
        turns = populated_section.get_turns_by_intent("intent_2")

        assert len(turns) == 1
        assert "intent_2" in turns[0].intents

    def test_search_key_phrases(self, populated_section: HistoryRecentSection) -> None:
        """Test searching key phrases."""
        turns = populated_section.search_key_phrases("phrase-3")

        assert len(turns) == 1
        assert any("phrase-3" in kp for kp in turns[0].key_phrases)

    def test_search_key_phrases_case_insensitive(self, section: HistoryRecentSection) -> None:
        """Test key phrase search is case insensitive."""
        section.add_compressed_turn(
            CompressedTurn(
                turn_id="t1",
                turn_number=11,
                key_phrases=["Meeting Tomorrow"],
            )
        )

        turns = section.search_key_phrases("meeting")

        assert len(turns) == 1

    def test_total_count(self, populated_section: HistoryRecentSection) -> None:
        """Test total turn count."""
        # 5 compressed + 3 summarized
        assert populated_section.total_count() == 8

    def test_is_archived(self, populated_section: HistoryRecentSection) -> None:
        """Test checking if turn is archived."""
        # Evict to create archived turns
        populated_section.evict_partial(target_kb=0.5)

        archived = populated_section.get_archived_turn_ids()
        if archived:
            assert populated_section.is_archived(archived[0]) is True

        assert populated_section.is_archived("nonexistent") is False


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests for statistics API."""

    def test_get_statistics(self, populated_section: HistoryRecentSection) -> None:
        """Test getting statistics."""
        stats = populated_section.get_statistics()

        assert stats["compressed_count"] == 5
        assert stats["summarized_count"] == 3
        assert stats["total_count"] == 8
        assert stats["max_compressed"] == 20
        assert stats["max_summarized"] == 10
        assert stats["oldest_compressed"] == 11
        assert stats["newest_compressed"] == 15
        assert stats["oldest_summarized"] == 31
        assert stats["newest_summarized"] == 33
        assert stats["size_bytes"] > 0

    def test_statistics_empty(self, section: HistoryRecentSection) -> None:
        """Test statistics for empty section."""
        stats = section.get_statistics()

        assert stats["compressed_count"] == 0
        assert stats["summarized_count"] == 0
        assert stats["oldest_compressed"] == 0
        assert stats["newest_compressed"] == 0


# =============================================================================
# Integrity Tests
# =============================================================================


class TestIntegrity:
    """Tests for integrity verification."""

    def test_compute_integrity(self, populated_section: HistoryRecentSection) -> None:
        """Test computing integrity hash."""
        hash1 = populated_section.compute_integrity()

        assert len(hash1) == 64  # SHA256 hex
        assert hash1 == populated_section.compute_integrity()  # Deterministic

    def test_verify_integrity(self, populated_section: HistoryRecentSection) -> None:
        """Test verifying integrity."""
        populated_section.update_integrity()

        assert populated_section.verify_integrity() is True

    def test_verify_integrity_after_modification(
        self, populated_section: HistoryRecentSection
    ) -> None:
        """Test integrity fails after modification."""
        populated_section.update_integrity()

        # Modify
        populated_section.add_compressed_turn(CompressedTurn(turn_id="new", turn_number=100))

        assert populated_section.verify_integrity() is False

    def test_verify_no_hash(self, section: HistoryRecentSection) -> None:
        """Test verification passes with no hash set."""
        assert section.verify_integrity() is True


# =============================================================================
# FlatBuffer Serialization Tests
# =============================================================================


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_to_flatbuffer(self, populated_section: HistoryRecentSection) -> None:
        """Test serializing to FlatBuffer."""
        data = populated_section.to_flatbuffer()

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_from_flatbuffer(self, populated_section: HistoryRecentSection) -> None:
        """Test deserializing from FlatBuffer."""
        data = populated_section.to_flatbuffer()

        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        assert restored.compressed_count() == populated_section.compressed_count()
        assert restored.summarized_count() == populated_section.summarized_count()
        assert restored.get_session_summary() == populated_section.get_session_summary()

    def test_roundtrip_compressed(self, section: HistoryRecentSection) -> None:
        """Test roundtrip preserves compressed turns."""
        section.add_compressed_turn(
            CompressedTurn(
                turn_id="t1",
                turn_number=11,
                entities=["Alice", "Bob"],
                intents=["schedule"],
                key_phrases=["meeting tomorrow"],
                timestamp_ms=1700000000000,
                emotion="neutral",
                user_tokens=50,
                response_tokens=100,
            )
        )

        data = section.to_flatbuffer()
        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        turn = restored.get_compressed_turn("t1")
        assert turn is not None
        assert turn.entities == ["Alice", "Bob"]
        assert turn.intents == ["schedule"]
        assert turn.key_phrases == ["meeting tomorrow"]
        assert turn.emotion == "neutral"
        assert turn.user_tokens == 50
        assert turn.response_tokens == 100

    def test_roundtrip_summarized(self, section: HistoryRecentSection) -> None:
        """Test roundtrip preserves summarized turns."""
        section.add_summarized_turn(
            SummarizedTurn(
                turn_id="t31",
                turn_number=31,
                summary="Test summary",
                timestamp_ms=1700000000000,
                primary_intent="schedule",
                primary_entity="Alice",
            )
        )

        data = section.to_flatbuffer()
        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        turn = restored.get_summarized_turn("t31")
        assert turn is not None
        assert turn.summary == "Test summary"
        assert turn.primary_intent == "schedule"
        assert turn.primary_entity == "Alice"

    def test_roundtrip_session_summary(self, section: HistoryRecentSection) -> None:
        """Test roundtrip preserves session summary."""
        section.set_session_summary("Session about project planning")

        data = section.to_flatbuffer()
        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        assert restored.get_session_summary() == "Session about project planning"

    def test_roundtrip_archive_data(self, populated_section: HistoryRecentSection) -> None:
        """Test roundtrip preserves archive data."""
        populated_section.evict_partial(target_kb=1)

        data = populated_section.to_flatbuffer()
        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        assert restored.get_total_turns_archived() == populated_section.get_total_turns_archived()
        assert restored.get_bytes_evicted_total() == populated_section.get_bytes_evicted_total()

    def test_caching(self, populated_section: HistoryRecentSection) -> None:
        """Test FlatBuffer caching."""
        data1 = populated_section.to_flatbuffer()
        data2 = populated_section.to_flatbuffer()

        # Same reference (cached)
        assert data1 is data2

    def test_cache_invalidation(self, section: HistoryRecentSection) -> None:
        """Test cache invalidated on modification."""
        section.add_compressed_turn(CompressedTurn(turn_id="t1", turn_number=11))
        data1 = section.to_flatbuffer()

        section.add_compressed_turn(CompressedTurn(turn_id="t2", turn_number=12))
        data2 = section.to_flatbuffer()

        assert data1 is not data2


# =============================================================================
# Apply Operations Tests
# =============================================================================


class TestApplyOperations:
    """Tests for apply operations (MutationGuard pattern)."""

    def test_apply_add_compressed(self, section: HistoryRecentSection) -> None:
        """Test apply add_compressed."""
        result = section.apply(
            "add_compressed",
            {
                "turn": {
                    "turn_id": "t1",
                    "turn_number": 11,
                    "entities": ["Alice"],
                    "intents": ["schedule"],
                    "key_phrases": [],
                }
            },
        )

        assert result is True
        assert section.compressed_count() == 1

    def test_apply_add_summarized(self, section: HistoryRecentSection) -> None:
        """Test apply add_summarized."""
        result = section.apply(
            "add_summarized",
            {
                "turn": {
                    "turn_id": "t31",
                    "turn_number": 31,
                    "summary": "Test summary",
                }
            },
        )

        assert result is True
        assert section.summarized_count() == 1

    def test_apply_compress_to_summarized(self, section: HistoryRecentSection) -> None:
        """Test apply compress_to_summarized."""
        section.add_compressed_turn(CompressedTurn(turn_id="t1", turn_number=11))

        result = section.apply("compress_to_summarized", {"count": 1})

        assert len(result) == 1
        assert section.compressed_count() == 0
        assert section.summarized_count() == 1

    def test_apply_set_session_summary(self, section: HistoryRecentSection) -> None:
        """Test apply set_session_summary."""
        section.apply("set_session_summary", {"summary": "New summary"})

        assert section.get_session_summary() == "New summary"

    def test_apply_evict_partial(self, populated_section: HistoryRecentSection) -> None:
        """Test apply evict_partial."""
        result = populated_section.apply("evict_partial", {"target_kb": 0.5})

        assert isinstance(result, EvictedData)
        assert result.bytes_freed > 0

    def test_apply_clear(self, populated_section: HistoryRecentSection) -> None:
        """Test apply clear."""
        populated_section.apply("clear", {})

        assert populated_section.total_count() == 0

    def test_apply_unknown_operation(self, section: HistoryRecentSection) -> None:
        """Test apply with unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown", {})


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_history_recent_section(self) -> None:
        """Test factory creates empty section."""
        section = create_history_recent_section()

        assert isinstance(section, HistoryRecentSection)
        assert section.compressed_count() == 0
        assert section.summarized_count() == 0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_len(self, populated_section: HistoryRecentSection) -> None:
        """Test __len__ returns total count."""
        assert len(populated_section) == 8

    def test_repr(self, populated_section: HistoryRecentSection) -> None:
        """Test __repr__."""
        r = repr(populated_section)

        assert "HistoryRecentSection" in r
        assert "compressed=5" in r
        assert "summarized=3" in r

    def test_empty_entities_intents(self, section: HistoryRecentSection) -> None:
        """Test turn with empty entities/intents."""
        turn = CompressedTurn(turn_id="t1", turn_number=11)
        section.add_compressed_turn(turn)

        data = section.to_flatbuffer()
        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        t = restored.get_compressed_turn("t1")
        assert t is not None
        assert t.entities == []
        assert t.intents == []

    def test_unicode_content(self, section: HistoryRecentSection) -> None:
        """Test unicode in content."""
        section.add_compressed_turn(
            CompressedTurn(
                turn_id="t1",
                turn_number=11,
                entities=["Müller", "日本語"],
                key_phrases=["🎉 celebration"],
            )
        )
        section.set_session_summary("Session avec données françaises")

        data = section.to_flatbuffer()
        restored = HistoryRecentSection()
        restored.from_flatbuffer(data)

        t = restored.get_compressed_turn("t1")
        assert t is not None
        assert "Müller" in t.entities
        assert "日本語" in t.entities
        assert "🎉 celebration" in t.key_phrases
        assert "françaises" in restored.get_session_summary()

    def test_constants(self) -> None:
        """Test class constants."""
        assert HistoryRecentSection.BUDGET_BYTES == 20480
        assert HistoryRecentSection.TIER == "warm"
        assert HistoryRecentSection.SECTION_NAME == "history_recent"
        assert HistoryRecentSection.CAN_EVICT is True
        assert HistoryRecentSection.EVICTION_PRIORITY == 3
        assert HistoryRecentSection.MAX_COMPRESSED_TURNS == 20
        assert HistoryRecentSection.MAX_SUMMARIZED_TURNS == 10
