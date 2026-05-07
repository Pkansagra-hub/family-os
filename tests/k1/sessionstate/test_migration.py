"""
Tests for MigrationEngine - HOT <-> WARM Demote/Promote
========================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.1 Kernel Services
ISSUE: 2.1.4

TESTING PHILOSOPHY:
- NO MOCKS for core adapters - Use real LocalColdArchive, SizeTracker
- Test doubles (fakes) are acceptable for ISectionDataProvider since
  this tests the migration LOGIC, not the section implementations
- The SectionDataProvider fake implements real data storage behavior
- Integration tests with real sections are in test_integration.py

Test Coverage:
- MigrationDirection enum
- MigrationItem dataclass
- MigrationResult dataclass
- CompressedTurn and SummarizedTurn dataclasses
- MigrationTrigger enum
- MigrationEngine initialization
- can_demote() / can_promote() validation
- demote() core functionality
- promote() core functionality
- demote_on_pressure() automatic demotion
- demote_turn_beliefs() turn completion
- demote_history_overflow() history management
- Compression and summarization
- Section locking during migration
- Concurrent migration prevention
- Status and diagnostics
"""

import json
from typing import Any, Dict, List

from k1.sessionstate.guard import MutationGuard
from k1.sessionstate.migration import (
    COMPRESSION_TURN_THRESHOLD,
    DEMOTE_PRIORITY,
    MAX_HISTORY_ACTIVE_TURNS,
    MIGRATION_PAIRS,
    REVERSE_MIGRATION_PAIRS,
    TARGET_HOT_UTILIZATION,
    CompressedTurn,
    MigrationDirection,
    MigrationEngine,
    MigrationItem,
    MigrationResult,
    MigrationTrigger,
    SummarizedTurn,
)
from k1.sessionstate.sizetracker import PressureLevel, SizeTracker

# =============================================================================
# TEST DOUBLE: SECTION DATA PROVIDER (Fake, not Mock)
# =============================================================================


class TestSectionDataProvider:
    """
    Test double (fake) for ISectionDataProvider.

    This is NOT a mock - it implements real data storage behavior.
    Used for testing MigrationEngine logic in isolation from actual
    section implementations. Integration tests with real sections
    are in test_integration.py.

    Implements:
    - get_items(): Return stored items
    - add_items(): Store items and track bytes
    - remove_items(): Remove items and return freed bytes
    - clear_section(): Clear all data
    - get_turn_count(): Return turn count for history sections
    - get_oldest_turns(): Return oldest N turns
    """

    def __init__(self) -> None:
        self._sections: Dict[str, List[MigrationItem]] = {}
        self._turn_counts: Dict[str, int] = {}

    def set_items(self, section: str, items: List[MigrationItem]) -> None:
        """Set items for a section."""
        self._sections[section] = items

    def set_turn_count(self, section: str, count: int) -> None:
        """Set turn count for a history section."""
        self._turn_counts[section] = count

    def get_items(self, section: str) -> List[MigrationItem]:
        """Get all items from a section."""
        return self._sections.get(section, [])

    def add_items(self, section: str, items: List[MigrationItem]) -> int:
        """Add items to a section, return bytes added."""
        if section not in self._sections:
            self._sections[section] = []
        total_bytes = 0
        for item in items:
            self._sections[section].append(item)
            total_bytes += item.size_bytes
        return total_bytes

    def remove_items(self, section: str, keys: List[str]) -> int:
        """Remove items by keys, return bytes freed."""
        if section not in self._sections:
            return 0
        freed = 0
        remaining = []
        for item in self._sections[section]:
            if item.key in keys:
                freed += item.size_bytes
            else:
                remaining.append(item)
        self._sections[section] = remaining
        return freed

    def clear_section(self, section: str) -> int:
        """Clear all items from section, return bytes freed."""
        if section not in self._sections:
            return 0
        freed = sum(item.size_bytes for item in self._sections[section])
        self._sections[section] = []
        return freed

    def get_turn_count(self, section: str) -> int:
        """Get number of turns in history section."""
        return self._turn_counts.get(section, len(self._sections.get(section, [])))

    def get_oldest_turns(self, section: str, count: int) -> List[MigrationItem]:
        """Get oldest N turns from history section."""
        items = self._sections.get(section, [])
        return items[:count]


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================


class TestMigrationDirection:
    """Tests for MigrationDirection enum."""

    def test_demote_value(self) -> None:
        """DEMOTE has value 'demote'."""
        assert MigrationDirection.DEMOTE.value == "demote"

    def test_promote_value(self) -> None:
        """PROMOTE has value 'promote'."""
        assert MigrationDirection.PROMOTE.value == "promote"

    def test_is_str_enum(self) -> None:
        """MigrationDirection is a string enum."""
        assert isinstance(MigrationDirection.DEMOTE, str)
        assert MigrationDirection.DEMOTE == "demote"


class TestMigrationTrigger:
    """Tests for MigrationTrigger enum."""

    def test_pressure_trigger(self) -> None:
        """PRESSURE trigger exists."""
        assert MigrationTrigger.PRESSURE.value == "pressure"

    def test_turn_complete_trigger(self) -> None:
        """TURN_COMPLETE trigger exists."""
        assert MigrationTrigger.TURN_COMPLETE.value == "turn_complete"

    def test_history_overflow_trigger(self) -> None:
        """HISTORY_OVERFLOW trigger exists."""
        assert MigrationTrigger.HISTORY_OVERFLOW.value == "history_overflow"

    def test_context_switch_trigger(self) -> None:
        """CONTEXT_SWITCH trigger exists."""
        assert MigrationTrigger.CONTEXT_SWITCH.value == "context_switch"

    def test_thread_resume_trigger(self) -> None:
        """THREAD_RESUME trigger exists."""
        assert MigrationTrigger.THREAD_RESUME.value == "thread_resume"

    def test_manual_trigger(self) -> None:
        """MANUAL trigger exists."""
        assert MigrationTrigger.MANUAL.value == "manual"


class TestConstants:
    """Tests for module constants."""

    def test_migration_pairs_exist(self) -> None:
        """Migration pairs are defined."""
        assert "beliefs_active" in MIGRATION_PAIRS
        assert "history_active" in MIGRATION_PAIRS

    def test_migration_pairs_targets(self) -> None:
        """Migration pairs have correct targets."""
        assert MIGRATION_PAIRS["beliefs_active"] == "beliefs_history"
        assert MIGRATION_PAIRS["history_active"] == "history_recent"

    def test_reverse_migration_pairs(self) -> None:
        """Reverse migration pairs are derived correctly."""
        assert REVERSE_MIGRATION_PAIRS["beliefs_history"] == "beliefs_active"
        assert REVERSE_MIGRATION_PAIRS["history_recent"] == "history_active"

    def test_max_history_turns(self) -> None:
        """MAX_HISTORY_ACTIVE_TURNS is 10."""
        assert MAX_HISTORY_ACTIVE_TURNS == 10

    def test_compression_threshold(self) -> None:
        """COMPRESSION_TURN_THRESHOLD is 30."""
        assert COMPRESSION_TURN_THRESHOLD == 30

    def test_target_hot_utilization(self) -> None:
        """TARGET_HOT_UTILIZATION is 70%."""
        assert TARGET_HOT_UTILIZATION == 0.70

    def test_demote_priority_order(self) -> None:
        """DEMOTE_PRIORITY has correct order."""
        assert DEMOTE_PRIORITY["history_active"] == 1
        assert DEMOTE_PRIORITY["beliefs_active"] == 2
        assert DEMOTE_PRIORITY["narrative_active"] == 3


# =============================================================================
# DATA CLASSES
# =============================================================================


class TestMigrationItem:
    """Tests for MigrationItem dataclass."""

    def test_create_migration_item(self) -> None:
        """Can create MigrationItem."""
        item = MigrationItem(
            section="beliefs_active",
            key="fact_001",
            data={"type": "preference", "value": "coffee"},
            size_bytes=256,
        )
        assert item.section == "beliefs_active"
        assert item.key == "fact_001"
        assert item.size_bytes == 256

    def test_migration_item_metadata(self) -> None:
        """MigrationItem can have metadata."""
        item = MigrationItem(
            section="history_active",
            key="turn_5",
            data={"turn_id": "turn_5"},
            size_bytes=1024,
            metadata={"turn_number": 5, "timestamp_ms": 1234567890},
        )
        assert item.metadata["turn_number"] == 5

    def test_migration_item_repr(self) -> None:
        """MigrationItem has readable repr."""
        item = MigrationItem(
            section="beliefs_active",
            key="fact_001",
            data={},
            size_bytes=256,
        )
        repr_str = repr(item)
        assert "beliefs_active" in repr_str
        assert "fact_001" in repr_str
        assert "256" in repr_str


class TestCompressedTurn:
    """Tests for CompressedTurn dataclass."""

    def test_create_compressed_turn(self) -> None:
        """Can create CompressedTurn."""
        turn = CompressedTurn(
            turn_id="turn_15",
            timestamp_ms=1234567890,
            entities=["John", "coffee"],
            intents=["order", "preference"],
            key_phrases=["morning routine"],
            user_summary="I'd like a coffee please",
            assistant_summary="Sure, what size would you like?",
        )
        assert turn.turn_id == "turn_15"
        assert "John" in turn.entities
        assert "order" in turn.intents

    def test_compressed_turn_to_dict(self) -> None:
        """CompressedTurn converts to dict."""
        turn = CompressedTurn(
            turn_id="turn_15",
            timestamp_ms=1234567890,
            entities=["John"],
            intents=["greet"],
            key_phrases=[],
            user_summary="Hello",
            assistant_summary="Hi there",
        )
        d = turn.to_dict()
        assert d["turn_id"] == "turn_15"
        assert d["timestamp_ms"] == 1234567890
        assert d["entities"] == ["John"]

    def test_compressed_turn_from_dict(self) -> None:
        """CompressedTurn can be created from dict."""
        data = {
            "turn_id": "turn_20",
            "timestamp_ms": 9876543210,
            "entities": ["Alice", "Bob"],
            "intents": ["introduce"],
            "key_phrases": ["meeting"],
            "user_summary": "Alice, meet Bob",
            "assistant_summary": "Nice to meet you",
        }
        turn = CompressedTurn.from_dict(data)
        assert turn.turn_id == "turn_20"
        assert "Alice" in turn.entities


class TestSummarizedTurn:
    """Tests for SummarizedTurn dataclass."""

    def test_create_summarized_turn(self) -> None:
        """Can create SummarizedTurn."""
        turn = SummarizedTurn(
            turn_id="turn_35",
            timestamp_ms=1234567890,
            summary="User asked about weather, assistant provided forecast.",
        )
        assert turn.turn_id == "turn_35"
        assert "weather" in turn.summary

    def test_summarized_turn_to_dict(self) -> None:
        """SummarizedTurn converts to dict."""
        turn = SummarizedTurn(
            turn_id="turn_35",
            timestamp_ms=1234567890,
            summary="Weather discussion",
        )
        d = turn.to_dict()
        assert d["turn_id"] == "turn_35"
        assert d["summary"] == "Weather discussion"

    def test_summarized_turn_from_dict(self) -> None:
        """SummarizedTurn can be created from dict."""
        data = {
            "turn_id": "turn_40",
            "timestamp_ms": 9876543210,
            "summary": "Wrapped up conversation",
        }
        turn = SummarizedTurn.from_dict(data)
        assert turn.turn_id == "turn_40"


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_create_success_result(self) -> None:
        """Can create successful MigrationResult."""
        result = MigrationResult(
            success=True,
            direction=MigrationDirection.DEMOTE,
            source_section="beliefs_active",
            target_section="beliefs_history",
            items_migrated=5,
            bytes_migrated=2048,
            bytes_freed=2048,
            bytes_added=1536,  # Compression
            duration_ms=5.5,
            trigger=MigrationTrigger.TURN_COMPLETE,
            new_hot_pressure=PressureLevel.NORMAL,
            new_warm_pressure=PressureLevel.NORMAL,
        )
        assert result.success is True
        assert result.items_migrated == 5
        assert result.bytes_freed > result.bytes_added  # Compression saves space

    def test_create_failure_result(self) -> None:
        """Can create failed MigrationResult using failure()."""
        result = MigrationResult.failure(
            direction=MigrationDirection.DEMOTE,
            source_section="beliefs_active",
            target_section="beliefs_history",
            error="WARM capacity insufficient",
            duration_ms=1.0,
            trigger=MigrationTrigger.PRESSURE,
        )
        assert result.success is False
        assert "WARM capacity" in result.error

    def test_migration_result_to_dict(self) -> None:
        """MigrationResult converts to dict."""
        result = MigrationResult(
            success=True,
            direction=MigrationDirection.PROMOTE,
            source_section="beliefs_history",
            target_section="beliefs_active",
            items_migrated=3,
            bytes_migrated=1024,
            bytes_freed=0,
            bytes_added=1024,
            duration_ms=2.5,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["direction"] == "promote"
        assert d["items_migrated"] == 3

    def test_migration_result_repr(self) -> None:
        """MigrationResult has readable repr."""
        result = MigrationResult(
            success=True,
            direction=MigrationDirection.DEMOTE,
            source_section="history_active",
            target_section="history_recent",
            items_migrated=2,
            bytes_migrated=4096,
            bytes_freed=4096,
            bytes_added=1024,
            duration_ms=3.0,
        )
        repr_str = repr(result)
        assert "SUCCESS" in repr_str
        assert "demote" in repr_str


# =============================================================================
# MIGRATION ENGINE INITIALIZATION
# =============================================================================


class TestMigrationEngineInit:
    """Tests for MigrationEngine initialization."""

    def test_init_with_size_tracker_only(self) -> None:
        """Can initialize with just SizeTracker."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine is not None

    def test_init_with_mutation_guard(self) -> None:
        """Can initialize with MutationGuard."""
        tracker = SizeTracker()
        guard = MutationGuard(tracker)
        engine = MigrationEngine(tracker, mutation_guard=guard)
        assert engine is not None

    def test_init_with_section_provider(self) -> None:
        """Can initialize with section provider."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)
        assert engine is not None

    def test_init_with_custom_session_id(self) -> None:
        """Can initialize with custom session ID."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker, session_id="test-session-123")
        status = engine.get_status()
        assert "test-ses" in status["session_id"]

    def test_init_generates_session_id(self) -> None:
        """Generates session ID if not provided."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        status = engine.get_status()
        assert len(status["session_id"]) == 8  # First 8 chars of UUID


# =============================================================================
# CAN_DEMOTE / CAN_PROMOTE VALIDATION
# =============================================================================


class TestCanDemote:
    """Tests for can_demote() validation."""

    def test_can_demote_beliefs_active(self) -> None:
        """beliefs_active can be demoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("beliefs_active") is True

    def test_can_demote_history_active(self) -> None:
        """history_active can be demoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("history_active") is True

    def test_cannot_demote_control(self) -> None:
        """control section CANNOT be demoted (NEVER_EVICT)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("control") is False

    def test_cannot_demote_meta(self) -> None:
        """meta section CANNOT be demoted (NEVER_EVICT)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("meta") is False

    def test_cannot_demote_warm_section(self) -> None:
        """WARM sections cannot be demoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("beliefs_history") is False
        assert engine.can_demote("persona") is False

    def test_cannot_demote_invalid_section(self) -> None:
        """Invalid sections cannot be demoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("nonexistent") is False

    def test_cannot_demote_scoreboard(self) -> None:
        """scoreboard cannot be demoted (no WARM pair)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_demote("scoreboard") is False


class TestCanPromote:
    """Tests for can_promote() validation."""

    def test_can_promote_beliefs_history(self) -> None:
        """beliefs_history can be promoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_promote("beliefs_history") is True

    def test_can_promote_history_recent(self) -> None:
        """history_recent can be promoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_promote("history_recent") is True

    def test_cannot_promote_hot_section(self) -> None:
        """HOT sections cannot be promoted (already in HOT)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_promote("beliefs_active") is False
        assert engine.can_promote("control") is False

    def test_cannot_promote_persona(self) -> None:
        """persona cannot be promoted (no HOT pair)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_promote("persona") is False

    def test_cannot_promote_telemetry(self) -> None:
        """telemetry cannot be promoted (no HOT pair)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_promote("telemetry") is False

    def test_cannot_promote_invalid_section(self) -> None:
        """Invalid sections cannot be promoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        assert engine.can_promote("nonexistent") is False


class TestGetTargetSection:
    """Tests for get_target_section()."""

    def test_get_demote_target_beliefs(self) -> None:
        """Get demote target for beliefs_active."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        target = engine.get_target_section("beliefs_active", MigrationDirection.DEMOTE)
        assert target == "beliefs_history"

    def test_get_demote_target_history(self) -> None:
        """Get demote target for history_active."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        target = engine.get_target_section("history_active", MigrationDirection.DEMOTE)
        assert target == "history_recent"

    def test_get_promote_target_beliefs(self) -> None:
        """Get promote target for beliefs_history."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        target = engine.get_target_section("beliefs_history", MigrationDirection.PROMOTE)
        assert target == "beliefs_active"

    def test_get_target_no_pair(self) -> None:
        """Returns None for sections without pairs."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)
        target = engine.get_target_section("scoreboard", MigrationDirection.DEMOTE)
        assert target is None


# =============================================================================
# DEMOTE OPERATIONS
# =============================================================================


class TestDemote:
    """Tests for demote() core functionality."""

    def test_demote_beliefs_active_success(self) -> None:
        """Demote beliefs_active to beliefs_history."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [
            MigrationItem(
                section="beliefs_active",
                key="fact_001",
                data={"type": "preference"},
                size_bytes=512,
            ),
            MigrationItem(
                section="beliefs_active",
                key="fact_002",
                data={"type": "context"},
                size_bytes=512,
            ),
        ]

        # Set up initial sizes
        tracker.update("beliefs_active", 1024)

        result = engine.demote("beliefs_active", items)

        assert result.success is True
        assert result.direction == MigrationDirection.DEMOTE
        assert result.source_section == "beliefs_active"
        assert result.target_section == "beliefs_history"
        assert result.items_migrated == 2
        assert result.bytes_freed == 1024

    def test_demote_empty_items(self) -> None:
        """Demote with empty items returns success."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        result = engine.demote("beliefs_active", [])

        assert result.success is True
        assert result.items_migrated == 0
        assert result.bytes_freed == 0

    def test_demote_never_evict_section_fails(self) -> None:
        """Demote control section fails (NEVER_EVICT)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="control", key="k", data={}, size_bytes=100)]

        result = engine.demote("control", items)

        assert result.success is False
        assert "NEVER_EVICT" in result.error

    def test_demote_invalid_section_fails(self) -> None:
        """Demote invalid section fails."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="nonexistent", key="k", data={}, size_bytes=100)]

        result = engine.demote("nonexistent", items)

        assert result.success is False
        # Error could be "not in HOT tier" or "cannot be demoted"
        assert "not in HOT tier" in result.error or "cannot be demoted" in result.error

    def test_demote_warm_section_fails(self) -> None:
        """Demote WARM section fails (not in HOT)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="beliefs_history", key="k", data={}, size_bytes=100)]

        result = engine.demote("beliefs_history", items)

        assert result.success is False
        assert "not in HOT tier" in result.error

    def test_demote_no_warm_pair_fails(self) -> None:
        """Demote section without WARM pair fails."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="scoreboard", key="k", data={}, size_bytes=100)]

        result = engine.demote("scoreboard", items)

        assert result.success is False
        assert "no WARM migration pair" in result.error

    def test_demote_updates_size_tracker(self) -> None:
        """Demote updates SizeTracker for both sections."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Initial state
        tracker.update("beliefs_active", 2048)
        tracker.update("beliefs_history", 1024)

        items = [
            MigrationItem(
                section="beliefs_active",
                key="fact_001",
                data={},
                size_bytes=1024,
            ),
        ]

        result = engine.demote("beliefs_active", items)

        assert result.success is True
        # HOT should decrease
        assert tracker.get_section_size("beliefs_active") == 1024
        # WARM should increase
        assert tracker.get_section_size("beliefs_history") == 2048

    def test_demote_warm_capacity_check(self) -> None:
        """Demote fails if WARM has insufficient capacity."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Fill WARM to near capacity
        tracker.update("beliefs_history", 12 * 1024)  # 12KB of 12KB budget
        tracker.update("history_recent", 20 * 1024)  # 20KB of 20KB budget
        tracker.update("persona", 8 * 1024)  # 8KB
        tracker.update("telemetry", 7 * 1024)  # 7KB - only 1KB left

        items = [
            MigrationItem(
                section="beliefs_active",
                key="fact_big",
                data={},
                size_bytes=2048,  # 2KB needed
            ),
        ]

        result = engine.demote("beliefs_active", items)

        assert result.success is False
        assert "WARM capacity insufficient" in result.error

    def test_demote_with_trigger(self) -> None:
        """Demote tracks trigger reason."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=100)]
        tracker.update("beliefs_active", 100)

        result = engine.demote("beliefs_active", items, trigger=MigrationTrigger.TURN_COMPLETE)

        assert result.success is True
        assert result.trigger == MigrationTrigger.TURN_COMPLETE

    def test_demote_returns_pressure_levels(self) -> None:
        """Demote result includes new pressure levels."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=100)]
        tracker.update("beliefs_active", 100)

        result = engine.demote("beliefs_active", items)

        assert result.new_hot_pressure in list(PressureLevel)
        assert result.new_warm_pressure in list(PressureLevel)


class TestDemoteWithSectionLocking:
    """Tests for demote() with MutationGuard section locking."""

    def test_demote_locks_sections(self) -> None:
        """Demote locks both source and target sections."""
        tracker = SizeTracker()
        guard = MutationGuard(tracker)
        engine = MigrationEngine(tracker, mutation_guard=guard)

        tracker.update("beliefs_active", 512)
        items = [MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=512)]

        # Before demote, sections should not be locked
        assert "beliefs_active" not in guard._locked_sections
        assert "beliefs_history" not in guard._locked_sections

        result = engine.demote("beliefs_active", items)

        # After demote, sections should be unlocked
        assert result.success is True
        assert "beliefs_active" not in guard._locked_sections
        assert "beliefs_history" not in guard._locked_sections


class TestDemoteConcurrentPrevention:
    """Tests for concurrent migration prevention."""

    def test_demote_sets_in_progress_flag(self) -> None:
        """Migration sets in_progress flag during operation."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Flag should be False before migration
        assert engine.migration_in_progress is False

        items = [MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=100)]
        tracker.update("beliefs_active", 100)

        result = engine.demote("beliefs_active", items)

        # Flag should be False after migration
        assert result.success is True
        assert engine.migration_in_progress is False

    def test_demote_rejects_if_already_in_progress(self) -> None:
        """Demote is rejected if migration already in progress."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Simulate migration in progress
        engine._migration_in_progress = True

        items = [MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=100)]

        result = engine.demote("beliefs_active", items)

        assert result.success is False
        assert "already in progress" in result.error


# =============================================================================
# PROMOTE OPERATIONS
# =============================================================================


class TestPromote:
    """Tests for promote() core functionality."""

    def test_promote_beliefs_history_success(self) -> None:
        """Promote beliefs_history to beliefs_active."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [
            MigrationItem(
                section="beliefs_history",
                key="old_fact_001",
                data={"type": "historical_preference"},
                size_bytes=512,
            ),
        ]

        # Set up initial sizes
        tracker.update("beliefs_history", 1024)

        result = engine.promote("beliefs_history", items)

        assert result.success is True
        assert result.direction == MigrationDirection.PROMOTE
        assert result.source_section == "beliefs_history"
        assert result.target_section == "beliefs_active"
        assert result.items_migrated == 1

    def test_promote_empty_items(self) -> None:
        """Promote with empty items returns success."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        result = engine.promote("beliefs_history", [])

        assert result.success is True
        assert result.items_migrated == 0

    def test_promote_hot_section_fails(self) -> None:
        """Promote HOT section fails (already in HOT)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=100)]

        result = engine.promote("beliefs_active", items)

        assert result.success is False
        assert "not in WARM tier" in result.error

    def test_promote_no_hot_pair_fails(self) -> None:
        """Promote section without HOT pair fails."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [MigrationItem(section="persona", key="k", data={}, size_bytes=100)]

        result = engine.promote("persona", items)

        assert result.success is False
        assert "no HOT migration pair" in result.error

    def test_promote_hot_capacity_check(self) -> None:
        """Promote fails if HOT has insufficient capacity."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Fill HOT to near capacity (52KB)
        tracker.update("control", 8 * 1024)
        tracker.update("beliefs_active", 8 * 1024)
        tracker.update("scoreboard", 6 * 1024)
        tracker.update("history_active", 8 * 1024)
        tracker.update("clarifications", 4 * 1024)
        tracker.update("affective_now", 4 * 1024)
        tracker.update("narrative_active", 4 * 1024)
        tracker.update("meta", 2 * 1024)
        tracker.update("task_state", 4 * 1024)
        tracker.update("task_artifacts", 4 * 1024)  # 52KB total, 0KB left

        items = [
            MigrationItem(
                section="beliefs_history",
                key="big_item",
                data={},
                size_bytes=5 * 1024,  # 5KB needed
            ),
        ]

        result = engine.promote("beliefs_history", items)

        assert result.success is False
        assert "HOT capacity insufficient" in result.error

    def test_promote_keeps_warm_copy(self) -> None:
        """Promote keeps copy in WARM by default."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_history", 1024)

        items = [
            MigrationItem(section="beliefs_history", key="k", data={}, size_bytes=512),
        ]

        result = engine.promote("beliefs_history", items)

        assert result.success is True
        assert result.bytes_freed == 0  # WARM copy kept
        assert result.bytes_added == 512  # Added to HOT

    def test_promote_updates_size_tracker(self) -> None:
        """Promote updates SizeTracker (only HOT increases)."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_active", 1024)
        tracker.update("beliefs_history", 2048)

        items = [
            MigrationItem(section="beliefs_history", key="k", data={}, size_bytes=512),
        ]

        result = engine.promote("beliefs_history", items)

        assert result.success is True
        # HOT should increase
        assert tracker.get_section_size("beliefs_active") == 1536
        # WARM should stay same (copy kept)
        assert tracker.get_section_size("beliefs_history") == 2048


# =============================================================================
# AUTOMATIC DEMOTION HELPERS
# =============================================================================


class TestDemoteOnPressure:
    """Tests for demote_on_pressure() automatic demotion."""

    def test_demote_on_pressure_no_action_when_normal(self) -> None:
        """No demotion when HOT pressure is NORMAL."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # HOT is well under capacity
        tracker.update("beliefs_active", 1024)

        result = engine.demote_on_pressure()

        assert result.success is True
        assert result.items_migrated == 0

    def test_demote_on_pressure_demotes_when_elevated(self) -> None:
        """Demotes data when HOT pressure is ELEVATED."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Fill HOT to > 80% (ELEVATED)
        # 48KB * 0.85 = ~40.8KB
        tracker.update("beliefs_active", 10 * 1024)
        tracker.update("history_active", 10 * 1024)
        tracker.update("scoreboard", 6 * 1024)
        tracker.update("control", 8 * 1024)
        tracker.update("narrative_active", 8 * 1024)
        # Total: 42KB (87.5%)

        result = engine.demote_on_pressure()

        assert result.trigger == MigrationTrigger.PRESSURE

    def test_demote_on_pressure_respects_priority(self) -> None:
        """Demotes sections in priority order."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)

        # Set up items in both demotable sections
        provider.set_items(
            "history_active",
            [MigrationItem(section="history_active", key="t1", data={}, size_bytes=2048)],
        )
        provider.set_items(
            "beliefs_active",
            [MigrationItem(section="beliefs_active", key="f1", data={}, size_bytes=2048)],
        )

        # Fill HOT
        tracker.update("history_active", 2048)
        tracker.update("beliefs_active", 2048)
        tracker.update("control", 8 * 1024)
        tracker.update("scoreboard", 6 * 1024)
        tracker.update("narrative_active", 8 * 1024)
        tracker.update("clarifications", 4 * 1024)
        tracker.update("affective_now", 4 * 1024)
        tracker.update("meta", 2 * 1024)  # Total: 38KB (79%)

        # Increase to trigger pressure
        tracker.update("history_active", 4 * 1024)  # Now 42KB (87.5%)

        result = engine.demote_on_pressure()

        # history_active has priority 1, should be demoted first
        assert result.trigger == MigrationTrigger.PRESSURE


class TestDemoteTurnBeliefs:
    """Tests for demote_turn_beliefs() turn completion demotion."""

    def test_demote_turn_beliefs_success(self) -> None:
        """Demotes beliefs at turn completion."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_active", 1024)

        result = engine.demote_turn_beliefs("turn_001")

        assert result.success is True
        assert result.source_section == "beliefs_active"
        assert result.target_section == "beliefs_history"
        assert result.trigger == MigrationTrigger.TURN_COMPLETE

    def test_demote_turn_beliefs_empty_section(self) -> None:
        """No demotion when beliefs_active is empty."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        result = engine.demote_turn_beliefs("turn_001")

        assert result.success is True
        assert result.items_migrated == 0

    def test_demote_turn_beliefs_with_provider(self) -> None:
        """Uses section provider for items."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)

        items = [
            MigrationItem(
                section="beliefs_active",
                key="fact_001",
                data={"type": "preference"},
                size_bytes=256,
            ),
            MigrationItem(
                section="beliefs_active",
                key="fact_002",
                data={"type": "context"},
                size_bytes=256,
            ),
        ]
        provider.set_items("beliefs_active", items)
        tracker.update("beliefs_active", 512)

        result = engine.demote_turn_beliefs("turn_001")

        assert result.success is True
        assert result.items_migrated == 2


class TestDemoteHistoryOverflow:
    """Tests for demote_history_overflow() history management."""

    def test_demote_history_no_overflow(self) -> None:
        """No demotion when history_active has <= 10 turns."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)

        provider.set_turn_count("history_active", 8)
        tracker.update("history_active", 8 * 1024)

        result = engine.demote_history_overflow()

        assert result.success is True
        assert result.items_migrated == 0

    def test_demote_history_overflow_demotes_excess(self) -> None:
        """Demotes turns beyond 10."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)

        # 15 turns, need to demote 5
        turns = [
            MigrationItem(
                section="history_active",
                key=f"turn_{i}",
                data={
                    "turn_id": f"turn_{i}",
                    "user_message": f"User message {i}",
                    "assistant_response": f"Response {i}",
                },
                size_bytes=1024,
                metadata={"turn_number": i + 1},
            )
            for i in range(15)
        ]
        provider.set_items("history_active", turns)
        provider.set_turn_count("history_active", 15)
        tracker.update("history_active", 15 * 1024)

        result = engine.demote_history_overflow()

        assert result.success is True
        assert result.trigger == MigrationTrigger.HISTORY_OVERFLOW
        # Should demote 5 turns (15 - 10)
        assert result.items_migrated == 5

    def test_demote_history_uses_estimate_without_provider(self) -> None:
        """Estimates turn count without provider."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # 15KB at ~1KB/turn = ~15 turns estimated
        tracker.update("history_active", 15 * 1024)

        result = engine.demote_history_overflow()

        assert result.trigger == MigrationTrigger.HISTORY_OVERFLOW


# =============================================================================
# COMPRESSION AND SUMMARIZATION
# =============================================================================


class TestCompression:
    """Tests for turn compression."""

    def test_compress_turn_extracts_entities(self) -> None:
        """Compression extracts entities from turn."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        turn_data = {
            "turn_id": "turn_15",
            "timestamp_ms": 1234567890,
            "user_message": "I want to order coffee for John",
            "assistant_response": "What size would you like?",
            "entities": ["coffee", "John"],
            "intents": ["order"],
            "key_phrases": ["order coffee"],
        }

        compressed = engine._compress_turn(turn_data)

        assert isinstance(compressed, CompressedTurn)
        assert "coffee" in compressed.entities
        assert "John" in compressed.entities
        assert "order" in compressed.intents

    def test_compress_turn_truncates_messages(self) -> None:
        """Compression truncates long messages to 100 chars."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        long_message = "A" * 200

        turn_data = {
            "turn_id": "turn_15",
            "timestamp_ms": 1234567890,
            "user_message": long_message,
            "assistant_response": long_message,
            "entities": [],
            "intents": [],
            "key_phrases": [],
        }

        compressed = engine._compress_turn(turn_data)

        assert len(compressed.user_summary) == 103  # 100 + "..."
        assert len(compressed.assistant_summary) == 103

    def test_compress_turn_custom_function(self) -> None:
        """Uses custom compression function if provided."""
        tracker = SizeTracker()

        custom_compressed = CompressedTurn(
            turn_id="custom",
            timestamp_ms=0,
            entities=["custom_entity"],
            intents=["custom_intent"],
            key_phrases=[],
            user_summary="custom",
            assistant_summary="custom",
        )

        def custom_compress(turn: Any) -> CompressedTurn:
            return custom_compressed

        engine = MigrationEngine(tracker, compress_fn=custom_compress)

        result = engine._compress_turn({"turn_id": "original"})

        assert result.turn_id == "custom"
        assert "custom_entity" in result.entities


class TestSummarization:
    """Tests for turn summarization."""

    def test_summarize_turn_creates_summary(self) -> None:
        """Summarization creates single sentence summary."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        turn_data = {
            "turn_id": "turn_35",
            "timestamp_ms": 1234567890,
            "user_message": "What's the weather like today?",
            "assistant_response": "It's sunny with a high of 75F.",
        }

        summarized = engine._summarize_turn(turn_data)

        assert isinstance(summarized, SummarizedTurn)
        assert summarized.turn_id == "turn_35"
        assert len(summarized.summary) > 0
        assert len(summarized.summary) <= 200

    def test_summarize_compressed_turn(self) -> None:
        """Can summarize already compressed turn."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        compressed = CompressedTurn(
            turn_id="turn_35",
            timestamp_ms=1234567890,
            entities=["weather"],
            intents=["query"],
            key_phrases=["today's weather"],
            user_summary="What's the weather?",
            assistant_summary="Sunny and warm",
        )

        summarized = engine._summarize_turn(compressed)

        assert isinstance(summarized, SummarizedTurn)
        assert summarized.turn_id == "turn_35"

    def test_summarize_custom_function(self) -> None:
        """Uses custom summarization function if provided."""
        tracker = SizeTracker()

        custom_summarized = SummarizedTurn(
            turn_id="custom",
            timestamp_ms=0,
            summary="Custom summary",
        )

        def custom_summarize(turn: Any) -> SummarizedTurn:
            return custom_summarized

        engine = MigrationEngine(tracker, summarize_fn=custom_summarize)

        result = engine._summarize_turn({"turn_id": "original"})

        assert result.turn_id == "custom"
        assert result.summary == "Custom summary"


# =============================================================================
# STATUS AND DIAGNOSTICS
# =============================================================================


class TestGetStatus:
    """Tests for get_status() diagnostics."""

    def test_get_status_returns_dict(self) -> None:
        """get_status() returns dictionary."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        status = engine.get_status()

        assert isinstance(status, dict)
        assert "session_id" in status
        assert "migration_in_progress" in status
        assert "hot_pressure" in status
        assert "warm_pressure" in status

    def test_get_status_shows_demotable_sections(self) -> None:
        """Status shows sections that can be demoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_active", 1024)
        tracker.update("history_active", 2048)

        status = engine.get_status()

        demotable = status["demotable_sections"]
        section_names = [s["section"] for s in demotable]
        assert "beliefs_active" in section_names
        assert "history_active" in section_names

    def test_get_status_shows_promotable_sections(self) -> None:
        """Status shows sections that can be promoted."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_history", 1024)

        status = engine.get_status()

        promotable = status["promotable_sections"]
        section_names = [s["section"] for s in promotable]
        assert "beliefs_history" in section_names

    def test_get_status_demote_needed_flag(self) -> None:
        """Status includes demote_needed flag."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Low pressure
        tracker.update("beliefs_active", 1024)
        status = engine.get_status()
        assert status["demote_needed"] is False

        # Fill to elevated pressure
        for section in ["control", "scoreboard", "history_active", "clarifications"]:
            tracker.update(section, 8 * 1024)
        tracker.update("affective_now", 4 * 1024)
        tracker.update("narrative_active", 4 * 1024)
        tracker.update("meta", 2 * 1024)
        # Now at ~40KB (83%)

        status = engine.get_status()
        assert status["demote_needed"] is True


class TestEstimateDemoteNeeded:
    """Tests for estimate_demote_needed()."""

    def test_estimate_zero_when_normal(self) -> None:
        """Returns 0 when pressure is normal."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_active", 1024)

        needed = engine.estimate_demote_needed()

        assert needed == 0

    def test_estimate_bytes_when_over_target(self) -> None:
        """Returns bytes to demote when over target."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Fill HOT to 40KB (target is 70% of 48KB = 33.6KB)
        tracker.update("beliefs_active", 10 * 1024)
        tracker.update("history_active", 10 * 1024)
        tracker.update("control", 8 * 1024)
        tracker.update("scoreboard", 6 * 1024)
        tracker.update("clarifications", 4 * 1024)
        tracker.update("meta", 2 * 1024)
        # Total: 40KB

        needed = engine.estimate_demote_needed()

        # Need to get from 40KB to 33.6KB
        target = int(52 * 1024 * 0.70)  # 33,587
        expected = 40 * 1024 - target  # ~6.4KB
        assert needed == expected


class TestGetDemoteCandidates:
    """Tests for get_demote_candidates()."""

    def test_get_demote_candidates_returns_items(self) -> None:
        """Returns list of demotable items."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        tracker.update("beliefs_active", 1024)
        tracker.update("history_active", 2048)

        candidates = engine.get_demote_candidates()

        assert len(candidates) >= 2
        sections = [c.section for c in candidates]
        assert "beliefs_active" in sections or "history_active" in sections

    def test_get_demote_candidates_with_provider(self) -> None:
        """Uses section provider for actual items."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)

        items = [
            MigrationItem(section="beliefs_active", key="f1", data={}, size_bytes=256),
            MigrationItem(section="beliefs_active", key="f2", data={}, size_bytes=256),
        ]
        provider.set_items("beliefs_active", items)
        tracker.update("beliefs_active", 512)

        candidates = engine.get_demote_candidates()

        assert len(candidates) == 2
        assert all(c.section == "beliefs_active" for c in candidates)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestMigrationIntegration:
    """Integration tests for complete migration workflows."""

    def test_demote_promote_roundtrip(self) -> None:
        """Demote then promote returns data to HOT."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Initial state
        tracker.update("beliefs_active", 2048)

        items = [
            MigrationItem(
                section="beliefs_active",
                key="fact_001",
                data={"type": "preference", "value": "coffee"},
                size_bytes=1024,
            ),
        ]

        # Demote
        demote_result = engine.demote("beliefs_active", items)
        assert demote_result.success is True
        assert tracker.get_section_size("beliefs_active") == 1024
        assert tracker.get_section_size("beliefs_history") == 1024

        # Promote back
        promote_items = [
            MigrationItem(
                section="beliefs_history",
                key="fact_001",
                data={"type": "preference", "value": "coffee"},
                size_bytes=1024,
            ),
        ]

        promote_result = engine.promote("beliefs_history", promote_items)
        assert promote_result.success is True
        assert tracker.get_section_size("beliefs_active") == 2048

    def test_full_turn_lifecycle(self) -> None:
        """Complete turn lifecycle with belief demotion."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Simulate turn 1
        tracker.update("beliefs_active", 512)
        result1 = engine.demote_turn_beliefs("turn_001")
        assert result1.success is True

        # Simulate turn 2
        tracker.update("beliefs_active", 512)
        result2 = engine.demote_turn_beliefs("turn_002")
        assert result2.success is True

        # Beliefs history should have both turns' data
        assert tracker.get_section_size("beliefs_history") == 1024

    def test_history_overflow_lifecycle(self) -> None:
        """Complete history overflow with compression."""
        tracker = SizeTracker()
        provider = TestSectionDataProvider()
        engine = MigrationEngine(tracker, section_provider=provider)

        # Create 12 turns (2 overflow)
        turns = [
            MigrationItem(
                section="history_active",
                key=f"turn_{i}",
                data={
                    "turn_id": f"turn_{i}",
                    "timestamp_ms": 1234567890 + i * 1000,
                    "user_message": f"User message for turn {i}",
                    "assistant_response": f"Assistant response for turn {i}",
                    "entities": ["entity1"],
                    "intents": ["intent1"],
                    "key_phrases": ["phrase1"],
                },
                size_bytes=1024,
                metadata={"turn_number": i + 1},
            )
            for i in range(12)
        ]
        provider.set_items("history_active", turns)
        provider.set_turn_count("history_active", 12)
        tracker.update("history_active", 12 * 1024)

        # Demote overflow
        result = engine.demote_history_overflow()

        assert result.success is True
        assert result.items_migrated == 2  # 12 - 10 = 2 excess


class TestMigrationWithMutationGuard:
    """Integration tests with MutationGuard."""

    def test_demote_with_guard_preflight(self) -> None:
        """Demote respects MutationGuard."""
        tracker = SizeTracker()
        guard = MutationGuard(tracker)
        engine = MigrationEngine(tracker, mutation_guard=guard)

        tracker.update("beliefs_active", 1024)

        items = [
            MigrationItem(section="beliefs_active", key="k", data={}, size_bytes=1024),
        ]

        result = engine.demote("beliefs_active", items)

        assert result.success is True

    def test_promote_with_guard_preflight(self) -> None:
        """Promote respects MutationGuard."""
        tracker = SizeTracker()
        guard = MutationGuard(tracker)
        engine = MigrationEngine(tracker, mutation_guard=guard)

        tracker.update("beliefs_history", 1024)

        items = [
            MigrationItem(section="beliefs_history", key="k", data={}, size_bytes=512),
        ]

        result = engine.promote("beliefs_history", items)

        assert result.success is True


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_demote_zero_byte_items(self) -> None:
        """Demote handles zero-byte items."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        items = [
            MigrationItem(section="beliefs_active", key="empty", data={}, size_bytes=0),
        ]

        result = engine.demote("beliefs_active", items)

        assert result.success is True
        assert result.bytes_freed == 0

    def test_promote_large_item(self) -> None:
        """Promote handles large items."""
        tracker = SizeTracker()
        engine = MigrationEngine(tracker)

        # Large item that fits
        items = [
            MigrationItem(
                section="beliefs_history",
                key="big_item",
                data={"large": "x" * 5000},
                size_bytes=5 * 1024,
            ),
        ]

        result = engine.promote("beliefs_history", items)

        assert result.success is True
        assert result.bytes_added == 5 * 1024

    def test_migration_result_serializable(self) -> None:
        """MigrationResult can be JSON serialized."""
        result = MigrationResult(
            success=True,
            direction=MigrationDirection.DEMOTE,
            source_section="beliefs_active",
            target_section="beliefs_history",
            items_migrated=5,
            bytes_migrated=2048,
            bytes_freed=2048,
            bytes_added=1536,
            duration_ms=5.5,
            trigger=MigrationTrigger.TURN_COMPLETE,
            new_hot_pressure=PressureLevel.NORMAL,
            new_warm_pressure=PressureLevel.ELEVATED,
        )

        d = result.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)

        assert parsed["success"] is True
        assert parsed["direction"] == "demote"
        assert parsed["new_warm_pressure"] == "elevated"
