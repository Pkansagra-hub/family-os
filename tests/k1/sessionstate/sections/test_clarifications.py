"""
ClarificationsSection Tests
============================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.5 (clarifications)

Comprehensive test suite for ClarificationsSection.
Tests cover:
1. Initialization and properties
2. Request operations
3. Answer/cancel/expire operations
4. Query operations (find_by_*)
5. Option management
6. Priority management
7. Blocking state
8. Duplicate detection
9. FlatBuffer serialization/deserialization
10. Statistics and metadata
11. Edge cases and error handling
"""

import time

import pytest

from k1.sessionstate.sections.clarifications import (
    Clarification,
    ClarificationOption,
    ClarificationPriority,
    ClarificationsSection,
    QuestionStatus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> ClarificationsSection:
    """Create a fresh ClarificationsSection instance."""
    return ClarificationsSection(session_id="test-session-123")


@pytest.fixture
def sample_options() -> list[ClarificationOption]:
    """Create sample options list."""
    return [
        ClarificationOption(id="opt1", text="Option A", action="do_a", confidence=0.8),
        ClarificationOption(id="opt2", text="Option B", action="do_b", confidence=0.6),
        ClarificationOption(id="opt3", text="Option C", action="do_c", confidence=0.4),
    ]


@pytest.fixture
def section_with_clarifications(section: ClarificationsSection) -> ClarificationsSection:
    """Section with some pre-existing clarifications."""
    section.request(
        agent_id="planner",
        question="Which format?",
        priority=ClarificationPriority.NORMAL,
    )
    section.request(
        agent_id="executor",
        question="Which device?",
        priority=ClarificationPriority.HIGH,
    )
    section.request(
        agent_id="planner",
        question="What time?",
        priority=ClarificationPriority.URGENT,
        related_entity="time-entity",
        related_intent="schedule",
    )
    return section


# =============================================================================
# Test Class: Initialization
# =============================================================================


class TestClarificationsSectionInit:
    """Test ClarificationsSection initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        section = ClarificationsSection()
        assert section.session_id is not None
        assert len(section.session_id) > 0
        assert section.schema_version == "1.0.0"
        assert section.last_updated_ms > 0

    def test_init_with_session_id(self) -> None:
        """Test initialization with session_id."""
        section = ClarificationsSection(session_id="my-session")
        assert section.session_id == "my-session"

    def test_init_with_schema_version(self) -> None:
        """Test initialization with custom schema version."""
        section = ClarificationsSection(schema_version="2.0.0")
        assert section.schema_version == "2.0.0"

    def test_initial_state(self, section: ClarificationsSection) -> None:
        """Test initial state after creation."""
        assert section.total_pending == 0
        assert section.total_resolved_session == 0
        assert section.avg_resolution_time_ms == 0
        assert section.is_blocked is False
        assert section.blocking_clarification_id == ""
        assert section.has_pending() is False


# =============================================================================
# Test Class: ISection Protocol
# =============================================================================


class TestISectionProtocol:
    """Test ISection protocol compliance."""

    def test_name(self, section: ClarificationsSection) -> None:
        """Test name property."""
        assert section.name == "clarifications"

    def test_tier(self, section: ClarificationsSection) -> None:
        """Test tier property."""
        assert section.tier == "hot"

    def test_budget_bytes(self, section: ClarificationsSection) -> None:
        """Test budget_bytes property."""
        assert section.budget_bytes == 4096  # 4KB

    def test_can_evict(self, section: ClarificationsSection) -> None:
        """Test can_evict property."""
        assert section.can_evict is False

    def test_get_size_bytes_empty(self, section: ClarificationsSection) -> None:
        """Test get_size_bytes for empty section."""
        size = section.get_size_bytes()
        assert size > 0  # Header overhead
        assert size <= section.budget_bytes

    def test_get_size_bytes_with_data(
        self, section_with_clarifications: ClarificationsSection
    ) -> None:
        """Test get_size_bytes with data."""
        size = section_with_clarifications.get_size_bytes()
        assert size > 100  # More than header
        assert size <= section_with_clarifications.budget_bytes

    def test_clear(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test clear method."""
        section_with_clarifications.clear()
        assert section_with_clarifications.total_pending == 0
        assert section_with_clarifications.total_resolved_session == 0
        assert section_with_clarifications.is_blocked is False
        assert section_with_clarifications.has_pending() is False

    def test_get_metadata(self, section: ClarificationsSection) -> None:
        """Test get_metadata returns expected keys."""
        section.request(agent_id="test", question="Test?")
        metadata = section.get_metadata()

        assert metadata["name"] == "clarifications"
        assert metadata["tier"] == "hot"
        assert metadata["budget_bytes"] == 4096
        assert "current_size_bytes" in metadata
        assert "utilization_pct" in metadata
        assert metadata["pending_count"] == 1
        assert metadata["recently_resolved_count"] == 0
        assert "is_blocked" in metadata


# =============================================================================
# Test Class: Request Operations
# =============================================================================


class TestRequestOperations:
    """Test clarification request operations."""

    def test_request_basic(self, section: ClarificationsSection) -> None:
        """Test basic clarification request."""
        clarification = section.request(
            agent_id="planner",
            question="Which option?",
        )
        assert clarification.id is not None
        assert clarification.agent_id == "planner"
        assert clarification.question == "Which option?"
        assert clarification.status == QuestionStatus.OPEN
        assert clarification.priority == ClarificationPriority.NORMAL
        assert clarification.created_at_ms > 0

    def test_request_with_options(
        self, section: ClarificationsSection, sample_options: list[ClarificationOption]
    ) -> None:
        """Test request with predefined options."""
        clarification = section.request(
            agent_id="planner",
            question="Choose one?",
            options=sample_options,
        )
        assert len(clarification.options) == 3
        assert clarification.options[0].id == "opt1"
        assert clarification.options[0].text == "Option A"

    def test_request_with_priority(self, section: ClarificationsSection) -> None:
        """Test request with priority levels."""
        c1 = section.request(agent_id="a", question="Q1", priority=ClarificationPriority.NORMAL)
        c2 = section.request(agent_id="a", question="Q2", priority=ClarificationPriority.HIGH)
        c3 = section.request(agent_id="a", question="Q3", priority=ClarificationPriority.URGENT)

        assert c1.priority == ClarificationPriority.NORMAL
        assert c2.priority == ClarificationPriority.HIGH
        assert c3.priority == ClarificationPriority.URGENT

    def test_request_with_context(self, section: ClarificationsSection) -> None:
        """Test request with related entity and intent."""
        clarification = section.request(
            agent_id="planner",
            question="Which device?",
            related_entity="device-123",
            related_intent="control",
        )
        assert clarification.related_entity == "device-123"
        assert clarification.related_intent == "control"

    def test_request_with_timeout(self, section: ClarificationsSection) -> None:
        """Test request with custom timeout."""
        clarification = section.request(
            agent_id="planner",
            question="Quick response?",
            timeout_ms=60000,  # 1 minute
        )
        assert clarification.timeout_ms == 60000

    def test_request_default_timeout(self, section: ClarificationsSection) -> None:
        """Test request uses default timeout."""
        clarification = section.request(agent_id="planner", question="Q?")
        assert clarification.timeout_ms == 5 * 60 * 1000  # 5 minutes

    def test_request_blocking(self, section: ClarificationsSection) -> None:
        """Test request with blocking flag."""
        clarification = section.request(
            agent_id="planner",
            question="Critical?",
            blocking=True,
        )
        assert clarification.is_blocking is True
        assert section.is_blocked is True
        assert section.blocking_clarification_id == clarification.id

    def test_request_custom_id(self, section: ClarificationsSection) -> None:
        """Test request with custom clarification ID."""
        clarification = section.request(
            agent_id="planner",
            question="Q?",
            clarification_id="custom-123",
        )
        assert clarification.id == "custom-123"

    def test_request_updates_pending_count(self, section: ClarificationsSection) -> None:
        """Test request increases pending count."""
        assert section.total_pending == 0
        section.request(agent_id="a", question="Q1")
        assert section.total_pending == 1
        section.request(agent_id="a", question="Q2")
        assert section.total_pending == 2

    def test_request_max_pending_exceeded(self, section: ClarificationsSection) -> None:
        """Test request raises error when max pending reached."""
        for i in range(ClarificationsSection.MAX_PENDING):
            section.request(agent_id="a", question=f"Q{i}")

        with pytest.raises(ValueError, match="Maximum pending clarifications"):
            section.request(agent_id="a", question="One more")


# =============================================================================
# Test Class: Get Operations
# =============================================================================


class TestGetOperations:
    """Test clarification get operations."""

    def test_get_existing(self, section: ClarificationsSection) -> None:
        """Test get existing clarification."""
        created = section.request(agent_id="a", question="Q?")
        retrieved = section.get(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.question == "Q?"

    def test_get_nonexistent(self, section: ClarificationsSection) -> None:
        """Test get non-existent clarification."""
        result = section.get("nonexistent-id")
        assert result is None


# =============================================================================
# Test Class: Answer Operations
# =============================================================================


class TestAnswerOperations:
    """Test clarification answer operations."""

    def test_answer_basic(self, section: ClarificationsSection) -> None:
        """Test basic answer operation."""
        clarification = section.request(agent_id="a", question="Q?")
        result = section.answer(clarification.id, "My answer")

        assert result is True
        # Clarification moved to recently_resolved
        assert section.get(clarification.id) is None
        resolved = section.list_recently_resolved()
        assert len(resolved) == 1
        assert resolved[0].status == QuestionStatus.ANSWERED
        assert resolved[0].answer == "My answer"

    def test_answer_with_option_selection(self, section: ClarificationsSection) -> None:
        """Test answer with selected option."""
        clarification = section.request(
            agent_id="a",
            question="Q?",
            options=[
                ClarificationOption(id="opt1", text="A"),
                ClarificationOption(id="opt2", text="B"),
            ],
        )
        result = section.answer(clarification.id, "A", selected_option_id="opt1")

        assert result is True
        resolved = section.list_recently_resolved()[0]
        assert resolved.selected_option_id == "opt1"

    def test_answer_nonexistent(self, section: ClarificationsSection) -> None:
        """Test answer non-existent clarification."""
        result = section.answer("nonexistent", "Answer")
        assert result is False

    def test_answer_updates_statistics(self, section: ClarificationsSection) -> None:
        """Test answer updates statistics."""
        clarification = section.request(agent_id="a", question="Q?")
        # Small delay to have measurable resolution time
        time.sleep(0.01)
        section.answer(clarification.id, "Answer")

        assert section.total_resolved_session == 1
        assert section.avg_resolution_time_ms >= 0

    def test_answer_updates_pending_count(self, section: ClarificationsSection) -> None:
        """Test answer decreases pending count."""
        c1 = section.request(agent_id="a", question="Q1")
        c2 = section.request(agent_id="a", question="Q2")
        assert section.total_pending == 2

        section.answer(c1.id, "A1")
        assert section.total_pending == 1

        section.answer(c2.id, "A2")
        assert section.total_pending == 0

    def test_answer_clears_blocking(self, section: ClarificationsSection) -> None:
        """Test answer clears blocking state."""
        clarification = section.request(agent_id="a", question="Q?", blocking=True)
        assert section.is_blocked is True

        section.answer(clarification.id, "Answer")
        assert section.is_blocked is False
        assert section.blocking_clarification_id == ""

    def test_answer_sets_answered_at(self, section: ClarificationsSection) -> None:
        """Test answer sets answered_at_ms."""
        before = int(time.time() * 1000)
        clarification = section.request(agent_id="a", question="Q?")
        section.answer(clarification.id, "Answer")

        resolved = section.list_recently_resolved()[0]
        assert resolved.answered_at_ms >= before


# =============================================================================
# Test Class: Cancel Operations
# =============================================================================


class TestCancelOperations:
    """Test clarification cancel operations."""

    def test_cancel_basic(self, section: ClarificationsSection) -> None:
        """Test basic cancel operation."""
        clarification = section.request(agent_id="a", question="Q?")
        result = section.cancel(clarification.id)

        assert result is True
        assert section.get(clarification.id) is None
        resolved = section.list_recently_resolved()
        assert len(resolved) == 1
        assert resolved[0].status == QuestionStatus.CANCELLED

    def test_cancel_nonexistent(self, section: ClarificationsSection) -> None:
        """Test cancel non-existent clarification."""
        result = section.cancel("nonexistent")
        assert result is False

    def test_cancel_clears_blocking(self, section: ClarificationsSection) -> None:
        """Test cancel clears blocking state."""
        clarification = section.request(agent_id="a", question="Q?", blocking=True)
        assert section.is_blocked is True

        section.cancel(clarification.id)
        assert section.is_blocked is False


# =============================================================================
# Test Class: Expire Operations
# =============================================================================


class TestExpireOperations:
    """Test clarification expire operations."""

    def test_expire_basic(self, section: ClarificationsSection) -> None:
        """Test basic expire operation."""
        clarification = section.request(agent_id="a", question="Q?")
        result = section.expire(clarification.id)

        assert result is True
        assert section.get(clarification.id) is None
        resolved = section.list_recently_resolved()
        assert len(resolved) == 1
        assert resolved[0].status == QuestionStatus.EXPIRED

    def test_expire_nonexistent(self, section: ClarificationsSection) -> None:
        """Test expire non-existent clarification."""
        result = section.expire("nonexistent")
        assert result is False

    def test_expire_clears_blocking(self, section: ClarificationsSection) -> None:
        """Test expire clears blocking state."""
        clarification = section.request(agent_id="a", question="Q?", blocking=True)
        section.expire(clarification.id)
        assert section.is_blocked is False

    def test_expire_old(self, section: ClarificationsSection) -> None:
        """Test expire_old expires timed-out clarifications."""
        # Create clarification with very short timeout
        section.request(
            agent_id="a",
            question="Q1",
            timeout_ms=1,  # 1ms timeout
            clarification_id="c1",
        )
        section.request(
            agent_id="a",
            question="Q2",
            timeout_ms=1000000,  # Long timeout
            clarification_id="c2",
        )

        # Wait for first to expire
        time.sleep(0.01)

        expired_count = section.expire_old()
        assert expired_count == 1
        assert section.get("c1") is None
        assert section.get("c2") is not None

    def test_expire_old_no_expirations(self, section: ClarificationsSection) -> None:
        """Test expire_old when nothing needs expiring."""
        section.request(agent_id="a", question="Q?", timeout_ms=1000000)
        expired_count = section.expire_old()
        assert expired_count == 0


# =============================================================================
# Test Class: Query Operations
# =============================================================================


class TestQueryOperations:
    """Test clarification query operations."""

    def test_list_pending_empty(self, section: ClarificationsSection) -> None:
        """Test list_pending on empty section."""
        result = section.list_pending()
        assert result == []

    def test_list_pending_ordered(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test list_pending returns ordered by priority, then time."""
        result = section_with_clarifications.list_pending()

        # Should be ordered: URGENT, HIGH, NORMAL
        assert len(result) == 3
        assert result[0].priority == ClarificationPriority.URGENT
        assert result[1].priority == ClarificationPriority.HIGH
        assert result[2].priority == ClarificationPriority.NORMAL

    def test_list_recently_resolved(self, section: ClarificationsSection) -> None:
        """Test list_recently_resolved."""
        c1 = section.request(agent_id="a", question="Q1")
        c2 = section.request(agent_id="a", question="Q2")

        section.answer(c1.id, "A1")
        section.cancel(c2.id)

        resolved = section.list_recently_resolved()
        assert len(resolved) == 2

    def test_list_recently_resolved_max_5(self, section: ClarificationsSection) -> None:
        """Test recently_resolved keeps max 5."""
        for i in range(7):
            c = section.request(agent_id="a", question=f"Q{i}")
            section.answer(c.id, f"A{i}")

        resolved = section.list_recently_resolved()
        assert len(resolved) == 5

    def test_find_by_agent(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test find_by_agent."""
        planner_clarifications = section_with_clarifications.find_by_agent("planner")
        assert len(planner_clarifications) == 2

        executor_clarifications = section_with_clarifications.find_by_agent("executor")
        assert len(executor_clarifications) == 1

    def test_find_by_agent_empty(self, section: ClarificationsSection) -> None:
        """Test find_by_agent with no matches."""
        result = section.find_by_agent("nonexistent")
        assert result == []

    def test_find_by_entity(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test find_by_entity."""
        result = section_with_clarifications.find_by_entity("time-entity")
        assert len(result) == 1
        assert result[0].question == "What time?"

    def test_find_by_intent(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test find_by_intent."""
        result = section_with_clarifications.find_by_intent("schedule")
        assert len(result) == 1
        assert result[0].question == "What time?"

    def test_has_pending(self, section: ClarificationsSection) -> None:
        """Test has_pending."""
        assert section.has_pending() is False

        c = section.request(agent_id="a", question="Q?")
        assert section.has_pending() is True

        section.answer(c.id, "A")
        assert section.has_pending() is False


# =============================================================================
# Test Class: Duplicate Detection
# =============================================================================


class TestDuplicateDetection:
    """Test duplicate question detection."""

    def test_is_already_asked_exact_match(self, section: ClarificationsSection) -> None:
        """Test exact match detection."""
        section.request(agent_id="a", question="What is your name?")

        assert section.is_already_asked("What is your name?") is True
        assert section.is_already_asked("What is your age?") is False

    def test_is_already_asked_case_insensitive(self, section: ClarificationsSection) -> None:
        """Test case-insensitive matching."""
        section.request(agent_id="a", question="What is your name?")

        assert section.is_already_asked("WHAT IS YOUR NAME?") is True
        assert section.is_already_asked("what is your name?") is True

    def test_is_already_asked_whitespace(self, section: ClarificationsSection) -> None:
        """Test whitespace normalization."""
        section.request(agent_id="a", question="What is your name?")

        assert section.is_already_asked("  What is your name?  ") is True

    def test_is_already_asked_agent_filter(self, section: ClarificationsSection) -> None:
        """Test agent filter."""
        section.request(agent_id="planner", question="What time?")
        section.request(agent_id="executor", question="Which device?")

        assert section.is_already_asked("What time?", agent_id="planner") is True
        assert section.is_already_asked("What time?", agent_id="executor") is False

    def test_is_already_asked_resolved_not_matched(self, section: ClarificationsSection) -> None:
        """Test resolved clarifications are not matched."""
        c = section.request(agent_id="a", question="Test question?")
        assert section.is_already_asked("Test question?") is True

        section.answer(c.id, "Answer")
        assert section.is_already_asked("Test question?") is False


# =============================================================================
# Test Class: Blocking State
# =============================================================================


class TestBlockingState:
    """Test blocking state management."""

    def test_get_blocking(self, section: ClarificationsSection) -> None:
        """Test get_blocking."""
        assert section.get_blocking() is None

        c = section.request(agent_id="a", question="Q?", blocking=True)
        blocking = section.get_blocking()
        assert blocking is not None
        assert blocking.id == c.id

    def test_set_blocking(self, section: ClarificationsSection) -> None:
        """Test set_blocking."""
        c = section.request(agent_id="a", question="Q?")
        assert section.is_blocked is False

        result = section.set_blocking(c.id)
        assert result is True
        assert section.is_blocked is True
        assert section.blocking_clarification_id == c.id

    def test_set_blocking_nonexistent(self, section: ClarificationsSection) -> None:
        """Test set_blocking on non-existent clarification."""
        result = section.set_blocking("nonexistent")
        assert result is False
        assert section.is_blocked is False

    def test_clear_blocking(self, section: ClarificationsSection) -> None:
        """Test clear_blocking."""
        c = section.request(agent_id="a", question="Q?", blocking=True)
        assert section.is_blocked is True

        section.clear_blocking()
        assert section.is_blocked is False
        assert section.blocking_clarification_id == ""
        # Clarification is still pending, just not blocking
        assert section.get(c.id) is not None
        assert section.get(c.id).is_blocking is False


# =============================================================================
# Test Class: Option Management
# =============================================================================


class TestOptionManagement:
    """Test clarification option management."""

    def test_add_option(self, section: ClarificationsSection) -> None:
        """Test add_option."""
        c = section.request(agent_id="a", question="Q?")
        result = section.add_option(c.id, "opt1", "Option A", "action_a", 0.9)

        assert result is True
        options = section.get_options(c.id)
        assert len(options) == 1
        assert options[0].id == "opt1"
        assert options[0].text == "Option A"
        assert options[0].action == "action_a"
        assert options[0].confidence == 0.9

    def test_add_option_nonexistent(self, section: ClarificationsSection) -> None:
        """Test add_option on non-existent clarification."""
        result = section.add_option("nonexistent", "opt1", "Text")
        assert result is False

    def test_get_options_empty(self, section: ClarificationsSection) -> None:
        """Test get_options when no options."""
        c = section.request(agent_id="a", question="Q?")
        options = section.get_options(c.id)
        assert options == []

    def test_get_options_nonexistent(self, section: ClarificationsSection) -> None:
        """Test get_options on non-existent clarification."""
        options = section.get_options("nonexistent")
        assert options == []

    def test_options_preserved_on_answer(
        self, section: ClarificationsSection, sample_options: list[ClarificationOption]
    ) -> None:
        """Test options are preserved when answered."""
        c = section.request(agent_id="a", question="Q?", options=sample_options)
        section.answer(c.id, "Option A", selected_option_id="opt1")

        resolved = section.list_recently_resolved()[0]
        assert len(resolved.options) == 3


# =============================================================================
# Test Class: Priority Management
# =============================================================================


class TestPriorityManagement:
    """Test priority management."""

    def test_update_priority(self, section: ClarificationsSection) -> None:
        """Test update_priority."""
        c = section.request(agent_id="a", question="Q?")
        assert c.priority == ClarificationPriority.NORMAL

        result = section.update_priority(c.id, ClarificationPriority.URGENT)
        assert result is True
        assert section.get(c.id).priority == ClarificationPriority.URGENT

    def test_update_priority_nonexistent(self, section: ClarificationsSection) -> None:
        """Test update_priority on non-existent clarification."""
        result = section.update_priority("nonexistent", ClarificationPriority.HIGH)
        assert result is False

    def test_get_urgent(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test get_urgent."""
        urgent = section_with_clarifications.get_urgent()
        assert len(urgent) == 1
        assert urgent[0].priority == ClarificationPriority.URGENT

    def test_get_high_priority(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test get_high_priority."""
        high = section_with_clarifications.get_high_priority()
        assert len(high) == 2  # HIGH and URGENT


# =============================================================================
# Test Class: Statistics
# =============================================================================


class TestStatistics:
    """Test statistics tracking."""

    def test_total_pending(self, section: ClarificationsSection) -> None:
        """Test total_pending."""
        assert section.total_pending == 0

        c1 = section.request(agent_id="a", question="Q1")
        assert section.total_pending == 1

        c2 = section.request(agent_id="a", question="Q2")
        assert section.total_pending == 2

        section.answer(c1.id, "A1")
        assert section.total_pending == 1

    def test_total_resolved_session(self, section: ClarificationsSection) -> None:
        """Test total_resolved_session counts all resolutions."""
        c1 = section.request(agent_id="a", question="Q1")
        c2 = section.request(agent_id="a", question="Q2")
        c3 = section.request(agent_id="a", question="Q3")

        section.answer(c1.id, "A")
        section.cancel(c2.id)
        section.expire(c3.id)

        # Only answered clarifications count in total_resolved
        # (based on implementation - cancel/expire don't increment)
        assert section.total_resolved_session == 1

    def test_avg_resolution_time(self, section: ClarificationsSection) -> None:
        """Test avg_resolution_time_ms."""
        c1 = section.request(agent_id="a", question="Q1")
        time.sleep(0.01)
        section.answer(c1.id, "A1")

        c2 = section.request(agent_id="a", question="Q2")
        time.sleep(0.02)
        section.answer(c2.id, "A2")

        assert section.total_resolved_session == 2
        assert section.avg_resolution_time_ms > 0


# =============================================================================
# Test Class: FlatBuffer Serialization
# =============================================================================


class TestFlatBufferSerialization:
    """Test FlatBuffer serialization/deserialization."""

    def test_roundtrip_empty(self, section: ClarificationsSection) -> None:
        """Test roundtrip of empty section."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

        new_section = ClarificationsSection()
        new_section.from_flatbuffer(data)

        assert new_section.total_pending == 0
        assert new_section.is_blocked is False

    def test_roundtrip_with_pending(self, section: ClarificationsSection) -> None:
        """Test roundtrip with pending clarifications."""
        c1 = section.request(
            agent_id="planner",
            question="Which format?",
            priority=ClarificationPriority.HIGH,
            related_entity="entity-1",
            related_intent="intent-1",
            clarification_id="c1",
        )
        section.add_option(c1.id, "opt1", "Short", "do_short", 0.8)
        section.add_option(c1.id, "opt2", "Long", "do_long", 0.6)

        data = section.to_flatbuffer()
        new_section = ClarificationsSection()
        new_section.from_flatbuffer(data)

        assert new_section.total_pending == 1
        restored = new_section.get("c1")
        assert restored is not None
        assert restored.agent_id == "planner"
        assert restored.question == "Which format?"
        assert restored.priority == ClarificationPriority.HIGH
        assert restored.related_entity == "entity-1"
        assert restored.related_intent == "intent-1"
        assert len(restored.options) == 2
        assert restored.options[0].id == "opt1"

    def test_roundtrip_with_recently_resolved(self, section: ClarificationsSection) -> None:
        """Test roundtrip preserves recently_resolved."""
        c1 = section.request(agent_id="a", question="Q1", clarification_id="c1")
        c2 = section.request(agent_id="a", question="Q2", clarification_id="c2")

        section.answer(c1.id, "Answer 1", selected_option_id="opt1")
        section.cancel(c2.id)

        data = section.to_flatbuffer()
        new_section = ClarificationsSection()
        new_section.from_flatbuffer(data)

        resolved = new_section.list_recently_resolved()
        assert len(resolved) == 2

        answered = [r for r in resolved if r.status == QuestionStatus.ANSWERED]
        assert len(answered) == 1
        assert answered[0].answer == "Answer 1"

    def test_roundtrip_blocking_state(self, section: ClarificationsSection) -> None:
        """Test roundtrip preserves blocking state."""
        section.request(
            agent_id="a",
            question="Blocking?",
            blocking=True,
            clarification_id="blocking-c",
        )

        data = section.to_flatbuffer()
        new_section = ClarificationsSection()
        new_section.from_flatbuffer(data)

        assert new_section.is_blocked is True
        assert new_section.blocking_clarification_id == "blocking-c"

    def test_roundtrip_statistics(self, section: ClarificationsSection) -> None:
        """Test roundtrip preserves statistics."""
        c1 = section.request(agent_id="a", question="Q1")
        time.sleep(0.01)
        section.answer(c1.id, "A1")

        original_resolved = section.total_resolved_session
        original_avg = section.avg_resolution_time_ms

        data = section.to_flatbuffer()
        new_section = ClarificationsSection()
        new_section.from_flatbuffer(data)

        assert new_section.total_resolved_session == original_resolved
        # Average is approximated from stored value
        assert new_section.avg_resolution_time_ms == original_avg

    def test_cache_invalidation(self, section: ClarificationsSection) -> None:
        """Test cache is invalidated on modifications."""
        data1 = section.to_flatbuffer()
        section.request(agent_id="a", question="Q?")
        data2 = section.to_flatbuffer()

        assert data1 != data2

    def test_serialize_alias(self, section: ClarificationsSection) -> None:
        """Test serialize() is alias for to_flatbuffer()."""
        section.request(agent_id="a", question="Q?")
        assert section.serialize() == section.to_flatbuffer()

    def test_deserialize_alias(self, section: ClarificationsSection) -> None:
        """Test deserialize() is alias for from_flatbuffer()."""
        section.request(agent_id="a", question="Q?", clarification_id="c1")
        data = section.to_flatbuffer()

        new_section = ClarificationsSection()
        new_section.deserialize(data)

        assert new_section.get("c1") is not None


# =============================================================================
# Test Class: Legacy API
# =============================================================================


class TestLegacyAPI:
    """Test legacy API compatibility."""

    def test_get_pending_alias(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test get_pending() is alias for list_pending()."""
        assert (
            section_with_clarifications.get_pending() == section_with_clarifications.list_pending()
        )

    def test_get_answered(self, section: ClarificationsSection) -> None:
        """Test get_answered() returns answered from recently_resolved."""
        c1 = section.request(agent_id="a", question="Q1")
        c2 = section.request(agent_id="a", question="Q2")

        section.answer(c1.id, "A1")
        section.cancel(c2.id)

        answered = section.get_answered()
        assert len(answered) == 1
        assert answered[0].status == QuestionStatus.ANSWERED


# =============================================================================
# Test Class: Apply Operations
# =============================================================================


class TestApplyOperations:
    """Test apply() mutation operations."""

    def test_apply_request(self, section: ClarificationsSection) -> None:
        """Test apply request operation."""
        result = section.apply(
            "request",
            {
                "agent_id": "planner",
                "question": "Which one?",
                "priority": 1,
                "related_entity": "entity-1",
            },
        )
        assert isinstance(result, Clarification)
        assert result.agent_id == "planner"
        assert result.question == "Which one?"

    def test_apply_request_with_options(self, section: ClarificationsSection) -> None:
        """Test apply request with options."""
        result = section.apply(
            "request",
            {
                "agent_id": "planner",
                "question": "Choose?",
                "options": [
                    {"id": "opt1", "text": "A", "action": "do_a", "confidence": 0.8},
                    {"id": "opt2", "text": "B"},
                ],
            },
        )
        assert len(result.options) == 2

    def test_apply_answer(self, section: ClarificationsSection) -> None:
        """Test apply answer operation."""
        c = section.request(agent_id="a", question="Q?")
        result = section.apply(
            "answer",
            {
                "clarification_id": c.id,
                "answer": "My answer",
                "selected_option_id": "opt1",
            },
        )
        assert result is True

    def test_apply_cancel(self, section: ClarificationsSection) -> None:
        """Test apply cancel operation."""
        c = section.request(agent_id="a", question="Q?")
        result = section.apply("cancel", {"clarification_id": c.id})
        assert result is True

    def test_apply_expire(self, section: ClarificationsSection) -> None:
        """Test apply expire operation."""
        c = section.request(agent_id="a", question="Q?")
        result = section.apply("expire", {"clarification_id": c.id})
        assert result is True

    def test_apply_expire_old(self, section: ClarificationsSection) -> None:
        """Test apply expire_old operation."""
        section.request(agent_id="a", question="Q?", timeout_ms=1)
        time.sleep(0.01)
        result = section.apply("expire_old", {})
        assert result == 1

    def test_apply_set_blocking(self, section: ClarificationsSection) -> None:
        """Test apply set_blocking operation."""
        c = section.request(agent_id="a", question="Q?")
        result = section.apply("set_blocking", {"clarification_id": c.id})
        assert result is True
        assert section.is_blocked is True

    def test_apply_clear_blocking(self, section: ClarificationsSection) -> None:
        """Test apply clear_blocking operation."""
        section.request(agent_id="a", question="Q?", blocking=True)
        result = section.apply("clear_blocking", {})
        assert result is True
        assert section.is_blocked is False

    def test_apply_update_priority(self, section: ClarificationsSection) -> None:
        """Test apply update_priority operation."""
        c = section.request(agent_id="a", question="Q?")
        result = section.apply(
            "update_priority",
            {
                "clarification_id": c.id,
                "priority": 2,
            },
        )
        assert result is True
        assert section.get(c.id).priority == ClarificationPriority.URGENT

    def test_apply_unknown_operation(self, section: ClarificationsSection) -> None:
        """Test apply with unknown operation raises error."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown_op", {})


# =============================================================================
# Test Class: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_question(self, section: ClarificationsSection) -> None:
        """Test request with empty question."""
        c = section.request(agent_id="a", question="")
        assert c.question == ""

    def test_empty_agent_id(self, section: ClarificationsSection) -> None:
        """Test request with empty agent_id."""
        c = section.request(agent_id="", question="Q?")
        assert c.agent_id == ""

    def test_unicode_content(self, section: ClarificationsSection) -> None:
        """Test Unicode in questions and answers."""
        c = section.request(agent_id="a", question="日本語の質問?")
        section.answer(c.id, "答え")

        resolved = section.list_recently_resolved()[0]
        assert resolved.question == "日本語の質問?"
        assert resolved.answer == "答え"

    def test_unicode_roundtrip(self, section: ClarificationsSection) -> None:
        """Test Unicode survives roundtrip."""
        section.request(agent_id="a", question="Emoji 🎉?", clarification_id="c1")

        data = section.to_flatbuffer()
        new_section = ClarificationsSection()
        new_section.from_flatbuffer(data)

        assert new_section.get("c1").question == "Emoji 🎉?"

    def test_long_question(self, section: ClarificationsSection) -> None:
        """Test long question text."""
        long_q = "Q" * 1000
        c = section.request(agent_id="a", question=long_q)
        assert len(c.question) == 1000

    def test_many_options(self, section: ClarificationsSection) -> None:
        """Test many options on single clarification."""
        c = section.request(agent_id="a", question="Q?")
        for i in range(20):
            section.add_option(c.id, f"opt{i}", f"Option {i}")

        assert len(section.get_options(c.id)) == 20

    def test_concurrent_modifications(self, section: ClarificationsSection) -> None:
        """Test multiple modifications update timestamp."""
        initial_ts = section.last_updated_ms

        time.sleep(0.01)
        section.request(agent_id="a", question="Q?")
        after_request = section.last_updated_ms
        assert after_request >= initial_ts

        time.sleep(0.01)
        section.clear()
        after_clear = section.last_updated_ms
        assert after_clear >= after_request


# =============================================================================
# Test Class: Index Integrity
# =============================================================================


class TestIndexIntegrity:
    """Test index integrity after operations."""

    def test_agent_index_after_answer(self, section: ClarificationsSection) -> None:
        """Test agent index is updated after answer."""
        c1 = section.request(agent_id="planner", question="Q1")
        c2 = section.request(agent_id="planner", question="Q2")

        assert len(section.find_by_agent("planner")) == 2

        section.answer(c1.id, "A1")
        assert len(section.find_by_agent("planner")) == 1

    def test_entity_index_after_cancel(self, section: ClarificationsSection) -> None:
        """Test entity index is updated after cancel."""
        section.request(
            agent_id="a",
            question="Q?",
            related_entity="entity-1",
            clarification_id="c1",
        )
        assert len(section.find_by_entity("entity-1")) == 1

        section.cancel("c1")
        assert len(section.find_by_entity("entity-1")) == 0

    def test_intent_index_after_expire(self, section: ClarificationsSection) -> None:
        """Test intent index is updated after expire."""
        section.request(
            agent_id="a",
            question="Q?",
            related_intent="intent-1",
            clarification_id="c1",
        )
        assert len(section.find_by_intent("intent-1")) == 1

        section.expire("c1")
        assert len(section.find_by_intent("intent-1")) == 0

    def test_indexes_after_clear(self, section_with_clarifications: ClarificationsSection) -> None:
        """Test all indexes are cleared on clear()."""
        assert len(section_with_clarifications.find_by_agent("planner")) > 0

        section_with_clarifications.clear()

        assert section_with_clarifications.find_by_agent("planner") == []
        assert section_with_clarifications.find_by_entity("time-entity") == []
        assert section_with_clarifications.find_by_intent("schedule") == []
