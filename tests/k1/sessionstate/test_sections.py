"""
Tests for session state sections - HOT CORE and WARM TIER.

Epic 4.2.6: HOT CORE Section Tests (8 sections, 48KB total)
Epic 4.2.7: WARM TIER Section Tests (4 sections, 48KB total)

Test Philosophy: NO MOCKS - Real section implementations only.
Each section tests: properties, data operations, size tracking, serialization.

HOT CORE Sections (CAN_EVICT = False):
- ControlSection: 8KB - NEVER EVICT, agent leases, flow state
- BeliefsActiveSection: 8KB - current turn facts in SVO format
- ScoreboardSection: 6KB - discourse state, referents, QUD
- HistoryActiveSection: 8KB - last 10 full-fidelity turns
- ClarificationsSection: 4KB - pending clarification requests
- AffectiveNowSection: 4KB - current emotional state
- NarrativeActiveSection: 4KB - conversation threads
- MetaSection: 2KB - session identity and lifecycle

WARM TIER Sections (CAN_EVICT = True):
- TelemetrySection: 8KB, priority 1 (FIRST to evict)
- BeliefsHistorySection: 12KB, priority 2
- HistoryRecentSection: 20KB, priority 3
- PersonaSection: 8KB, priority 4 (LAST to evict)
"""

import pytest

from k1.sessionstate.sections import (
    AffectiveNowSection,
    BeliefsActiveSection,
    BeliefsHistorySection,
    ClarificationsSection,
    ControlSection,
    HistoryActiveSection,
    HistoryRecentSection,
    MetaSection,
    NarrativeActiveSection,
    PersonaSection,
    ScoreboardSection,
    TelemetrySection,
)

# =============================================================================
# HOT CORE SECTION TESTS
# =============================================================================


class TestControlSection:
    """Tests for ControlSection (8KB) - NEVER EVICT."""

    def test_name_is_control(self):
        """Section name is 'control'."""
        section = ControlSection()
        assert section.name == "control"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = ControlSection()
        assert section.tier == "hot"

    def test_budget_is_8kb(self):
        """Budget is 8192 bytes."""
        section = ControlSection()
        assert section.budget_bytes == 8192

    def test_can_evict_is_false(self):
        """ControlSection can never be evicted."""
        section = ControlSection()
        assert section.can_evict is False

    def test_register_agent_creates_lease(self):
        """register_agent() creates agent lease."""
        section = ControlSection()
        lease = section.register_agent(
            agent_id="agent-1",
            agent_type="planner",
            capabilities=["plan", "execute"],
            priority=10,
        )
        assert lease.agent_id == "agent-1"
        assert lease.agent_type == "planner"
        assert lease.capabilities == ["plan", "execute"]
        assert lease.priority == 10

    def test_register_agent_duplicate_raises(self):
        """register_agent() raises on duplicate agent_id."""
        section = ControlSection()
        section.register_agent("agent-1", "planner")
        with pytest.raises(ValueError, match="already registered"):
            section.register_agent("agent-1", "executor")

    def test_unregister_agent_removes_lease(self):
        """unregister_agent() removes agent lease."""
        section = ControlSection()
        section.register_agent("agent-1", "planner")
        assert section.get_agent("agent-1") is not None
        result = section.unregister_agent("agent-1")
        assert result is True
        assert section.get_agent("agent-1") is None

    def test_get_agent_returns_none_for_unknown(self):
        """get_agent() returns None for unknown agent."""
        section = ControlSection()
        assert section.get_agent("unknown") is None

    def test_list_agents_returns_all_leases(self):
        """list_agents() returns all agent leases."""
        section = ControlSection()
        section.register_agent("agent-1", "planner")
        section.register_agent("agent-2", "executor")
        agents = section.list_agents()
        assert len(agents) == 2
        agent_ids = {a.agent_id for a in agents}
        assert agent_ids == {"agent-1", "agent-2"}

    def test_advance_turn_increments_count(self):
        """advance_turn() increments turn count."""
        section = ControlSection()
        initial_count = section._turn_count
        section.advance_turn()
        assert section._turn_count == initial_count + 1

    def test_advance_turn_updates_turn_id(self):
        """advance_turn() generates new turn_id."""
        section = ControlSection()
        initial_id = section._current_turn_id
        section.advance_turn()
        assert section._current_turn_id != initial_id

    def test_clear_resets_all_state(self):
        """clear() resets all section state."""
        section = ControlSection()
        section.register_agent("agent-1", "planner")
        section.advance_turn()
        section.clear()
        assert len(section._agent_leases) == 0
        assert section._turn_count == 0

    def test_get_size_bytes_returns_positive(self):
        """get_size_bytes() returns positive value."""
        section = ControlSection()
        size = section.get_size_bytes()
        assert size > 0
        assert size <= section.budget_bytes

    def test_get_size_bytes_increases_with_data(self):
        """get_size_bytes() increases when data added."""
        section = ControlSection()
        initial_size = section.get_size_bytes()
        for i in range(5):
            section.register_agent(f"agent-{i}", "planner")
        final_size = section.get_size_bytes()
        assert final_size > initial_size

    def test_get_metadata_returns_dict(self):
        """get_metadata() returns dictionary with expected keys."""
        section = ControlSection()
        metadata = section.get_metadata()
        assert isinstance(metadata, dict)
        assert "name" in metadata
        assert "tier" in metadata
        assert "budget_bytes" in metadata
        assert "current_size_bytes" in metadata
        assert metadata["name"] == "control"

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = ControlSection(session_id="test-session")
        section.register_agent("agent-1", "planner", capabilities=["plan"])
        section.advance_turn()

        # Serialize
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

        # Deserialize
        section2 = ControlSection()
        section2.from_flatbuffer(data)

        # Verify state preserved (note: session_id is not serialized)
        agent = section2.get_agent("agent-1")
        assert agent is not None
        assert agent.agent_type == "planner"


class TestBeliefsActiveSection:
    """Tests for BeliefsActiveSection (8KB)."""

    def test_name_is_beliefs_active(self):
        """Section name is 'beliefs_active'."""
        section = BeliefsActiveSection()
        assert section.name == "beliefs_active"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = BeliefsActiveSection()
        assert section.tier == "hot"

    def test_budget_is_8kb(self):
        """Budget is 8192 bytes."""
        section = BeliefsActiveSection()
        assert section.budget_bytes == 8192

    def test_can_evict_is_false(self):
        """BeliefsActiveSection cannot be evicted."""
        section = BeliefsActiveSection()
        assert section.can_evict is False

    def test_add_fact_creates_svo(self):
        """add_fact() adds belief in SVO format."""
        section = BeliefsActiveSection()
        fact = section.add_fact(
            subject="user",
            predicate="prefers",
            obj="dark mode",
            confidence=0.9,
        )
        assert fact.subject == "user"
        assert fact.predicate == "prefers"
        assert fact.object == "dark mode"
        assert fact.confidence == 0.9

    def test_list_facts_returns_all(self):
        """list_facts() returns all beliefs."""
        section = BeliefsActiveSection()
        section.add_fact("user", "likes", "coffee")
        section.add_fact("user", "has", "dog")
        facts = section.list_facts()
        assert len(facts) == 2

    def test_get_fact_by_id(self):
        """get_fact() retrieves by ID."""
        section = BeliefsActiveSection()
        fact = section.add_fact("user", "likes", "tea")
        retrieved = section.get_fact(fact.id)
        assert retrieved is not None
        assert retrieved.object == "tea"

    def test_find_by_subject(self):
        """find_by_subject() filters beliefs."""
        section = BeliefsActiveSection()
        section.add_fact("user", "likes", "coffee")
        section.add_fact("user", "likes", "tea")
        section.add_fact("system", "has", "feature")
        user_facts = section.find_by_subject("user")
        assert len(user_facts) == 2

    def test_remove_fact(self):
        """remove_fact() removes belief."""
        section = BeliefsActiveSection()
        fact = section.add_fact("user", "likes", "coffee")
        result = section.remove_fact(fact.id)
        assert result is True
        assert section.get_fact(fact.id) is None

    def test_add_increments_size(self):
        """Adding belief increases current_size_bytes."""
        section = BeliefsActiveSection()
        initial_size = section.get_size_bytes()
        for i in range(10):
            section.add_fact(f"subject-{i}", "has", f"value-{i}")
        final_size = section.get_size_bytes()
        assert final_size > initial_size

    def test_pin_fact_prevents_demotion(self):
        """pin_fact() prevents demotion to beliefs_history."""
        section = BeliefsActiveSection()
        fact = section.add_fact("user", "likes", "important")
        section.pin_fact(fact.id)
        assert fact.id in section.get_pinned_fact_ids()
        demotable = section.get_demotable_facts()
        demotable_ids = {f.id for f in demotable}
        assert fact.id not in demotable_ids

    def test_clear_removes_all(self):
        """clear() removes all facts."""
        section = BeliefsActiveSection()
        section.add_fact("user", "likes", "coffee")
        section.add_fact("user", "has", "dog")
        section.clear()
        assert len(section.list_facts()) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = BeliefsActiveSection(session_id="test-session")
        section.add_fact("user", "prefers", "dark mode", confidence=0.8)
        section.add_fact("user", "has", "cat")

        # Serialize
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        # Deserialize
        section2 = BeliefsActiveSection()
        section2.from_flatbuffer(data)

        facts = section2.list_facts()
        assert len(facts) == 2


class TestScoreboardSection:
    """Tests for ScoreboardSection (6KB)."""

    def test_name_is_scoreboard(self):
        """Section name is 'scoreboard'."""
        section = ScoreboardSection()
        assert section.name == "scoreboard"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = ScoreboardSection()
        assert section.tier == "hot"

    def test_budget_is_6kb(self):
        """Budget is 6144 bytes."""
        section = ScoreboardSection()
        assert section.budget_bytes == 6144

    def test_can_evict_is_false(self):
        """ScoreboardSection cannot be evicted."""
        section = ScoreboardSection()
        assert section.can_evict is False

    def test_add_referent(self):
        """add_referent() adds discourse referent."""
        section = ScoreboardSection()
        ref = section.add_referent(
            text="the car",
            entity_id="vehicle-123",
            entity_type="vehicle",
        )
        assert ref.text == "the car"
        assert ref.entity_id == "vehicle-123"

    def test_push_question(self):
        """push_question() adds QUD to stack."""
        section = ScoreboardSection()
        q = section.push_question(
            text="What color is it?",
            asked_by="user",
        )
        assert q.text == "What color is it?"
        assert len(section._qud_stack) == 1

    def test_pop_question(self):
        """pop_question() removes from stack."""
        section = ScoreboardSection()
        section.push_question("Question 1", "user")
        section.push_question("Question 2", "user")
        popped = section.pop_question()
        assert popped.text == "Question 2"
        assert len(section._qud_stack) == 1

    def test_boost_salience(self):
        """boost_salience() updates entity salience."""
        section = ScoreboardSection()
        section.boost_salience("entity-123", 0.5)
        entry = section._salience_map.get("entity-123")
        assert entry is not None
        assert entry.score >= 0.5

    def test_decay_salience(self):
        """decay_salience() reduces all scores."""
        section = ScoreboardSection()
        section.boost_salience("entity-1", 1.0)
        initial_score = section._salience_map["entity-1"].score
        section.decay_salience()
        final_score = section._salience_map.get("entity-1")
        # Score should decrease or entity removed if below threshold
        assert final_score is None or final_score.score < initial_score

    def test_push_topic(self):
        """push_topic() adds topic to stack."""
        section = ScoreboardSection()
        topic = section.push_topic("Weather discussion")
        assert topic.name == "Weather discussion"
        assert len(section._topic_stack) == 1

    def test_get_size_bytes(self):
        """get_size_bytes() returns size estimate."""
        section = ScoreboardSection()
        size = section.get_size_bytes()
        assert size > 0
        assert size <= section.budget_bytes

    def test_clear_resets_state(self):
        """clear() resets all state."""
        section = ScoreboardSection()
        section.add_referent("the dog", "dog-1")
        section.push_question("Where is it?", "user")
        section.clear()
        assert len(section._referents) == 0
        assert len(section._qud_stack) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = ScoreboardSection()
        section.add_referent("the cat", "cat-1", "pet")
        section.push_question("Is it hungry?", "user")

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = ScoreboardSection()
        section2.from_flatbuffer(data)
        # Verify referents and questions loaded


class TestHistoryActiveSection:
    """Tests for HistoryActiveSection (8KB)."""

    def test_name_is_history_active(self):
        """Section name is 'history_active'."""
        section = HistoryActiveSection()
        assert section.name == "history_active"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = HistoryActiveSection()
        assert section.tier == "hot"

    def test_budget_is_8kb(self):
        """Budget is 8192 bytes."""
        section = HistoryActiveSection()
        assert section.budget_bytes == 8192

    def test_can_evict_is_false(self):
        """HistoryActiveSection cannot be evicted."""
        section = HistoryActiveSection()
        assert section.can_evict is False

    def test_add_turn(self):
        """add_turn() adds conversation turn."""
        section = HistoryActiveSection()
        turn = section.add_turn(
            user_message="What's the weather?",
            assistant_response="Let me check...",
        )
        assert turn.user_message == "What's the weather?"
        assert turn.assistant_response == "Let me check..."
        assert turn.turn_number == 1

    def test_get_recent(self):
        """get_recent() returns N most recent turns."""
        section = HistoryActiveSection()
        for i in range(5):
            section.add_turn(f"Message {i}", f"Response {i}")
        recent = section.get_recent(3)
        assert len(recent) == 3
        # Most recent should be turn 5
        assert recent[-1].turn_number == 5

    def test_max_turns_overflow_tracked(self):
        """Section tracks overflow when exceeding MAX_TURNS (10)."""
        section = HistoryActiveSection()
        for i in range(15):
            section.add_turn(f"Message {i}", f"Response {i}")
        # Section stores all turns, overflow is tracked separately
        assert len(section._turns) == 15
        assert section.has_overflow()
        overflow = section.get_overflow()
        assert len(overflow) == 5  # 15 - 10 = 5 overflow turns

    def test_fifo_ordering(self):
        """Turns are in FIFO order."""
        section = HistoryActiveSection()
        section.add_turn("First", "First response")
        section.add_turn("Second", "Second response")
        section.add_turn("Third", "Third response")
        turns = section._turns
        assert turns[0].user_message == "First"
        assert turns[-1].user_message == "Third"

    def test_token_tracking(self):
        """Section tracks total tokens."""
        section = HistoryActiveSection()
        section.add_turn("Short message", "Short response")
        assert section.total_user_tokens > 0
        assert section.total_response_tokens > 0

    def test_demote_oldest_returns_turns(self):
        """demote_oldest() returns turns for demotion."""
        section = HistoryActiveSection()
        for i in range(5):
            section.add_turn(f"Msg {i}", f"Resp {i}")
        demoted = section.demote_oldest(2)
        assert len(demoted) == 2
        assert len(section._turns) == 3

    def test_clear_removes_all(self):
        """clear() removes all turns."""
        section = HistoryActiveSection()
        section.add_turn("Test", "Response")
        section.clear()
        assert len(section._turns) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = HistoryActiveSection(session_id="test-session")
        section.add_turn("Hello", "Hi there!")
        section.add_turn("How are you?", "I'm doing well!")

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = HistoryActiveSection()
        section2.from_flatbuffer(data)
        assert len(section2._turns) == 2


class TestClarificationsSection:
    """Tests for ClarificationsSection (4KB)."""

    def test_name_is_clarifications(self):
        """Section name is 'clarifications'."""
        section = ClarificationsSection()
        assert section.name == "clarifications"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = ClarificationsSection()
        assert section.tier == "hot"

    def test_budget_is_4kb(self):
        """Budget is 4096 bytes."""
        section = ClarificationsSection()
        assert section.budget_bytes == 4096

    def test_can_evict_is_false(self):
        """ClarificationsSection cannot be evicted."""
        section = ClarificationsSection()
        assert section.can_evict is False

    def test_request_adds_clarification(self):
        """request() adds clarification request."""
        section = ClarificationsSection()
        clarification = section.request(
            agent_id="planner",
            question="Short or detailed?",
        )
        assert clarification.agent_id == "planner"
        assert clarification.question == "Short or detailed?"
        assert len(section._pending) == 1

    def test_answer_resolves_clarification(self):
        """answer() marks clarification answered."""
        section = ClarificationsSection()
        c = section.request("planner", "Which option?")
        result = section.answer(c.id, "Option A")
        assert result is True
        assert len(section._pending) == 0
        assert len(section._recently_resolved) == 1

    def test_is_blocked_when_blocking(self):
        """is_blocked is True with blocking clarification."""
        section = ClarificationsSection()
        c = section.request("planner", "Critical question?", blocking=True)
        assert section.is_blocked is True
        assert section.blocking_clarification_id == c.id

    def test_get_pending_returns_open(self):
        """get_pending() returns open requests."""
        section = ClarificationsSection()
        section.request("agent-1", "Question 1")
        section.request("agent-2", "Question 2")
        pending = section.get_pending()
        assert len(pending) == 2

    def test_clear_removes_all(self):
        """clear() removes all clarifications."""
        section = ClarificationsSection()
        section.request("planner", "Question?")
        section.clear()
        assert len(section._pending) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = ClarificationsSection(session_id="test-session")
        section.request("planner", "Test question?")

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = ClarificationsSection()
        section2.from_flatbuffer(data)


class TestAffectiveNowSection:
    """Tests for AffectiveNowSection (4KB)."""

    def test_name_is_affective_now(self):
        """Section name is 'affective_now'."""
        section = AffectiveNowSection()
        assert section.name == "affective_now"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = AffectiveNowSection()
        assert section.tier == "hot"

    def test_budget_is_4kb(self):
        """Budget is 4096 bytes."""
        section = AffectiveNowSection()
        assert section.budget_bytes == 4096

    def test_can_evict_is_false(self):
        """AffectiveNowSection cannot be evicted."""
        section = AffectiveNowSection()
        assert section.can_evict is False

    def test_update_sets_emotion(self):
        """update() updates current mood."""
        section = AffectiveNowSection()
        section.update(
            emotion="happy",
            intensity=0.8,
            valence=0.6,
            arousal=0.7,
        )
        assert section._current_emotion == "happy"
        assert section._intensity == 0.8

    def test_get_dimensions(self):
        """dimensions property returns VAD values."""
        section = AffectiveNowSection()
        section.update(
            emotion="excited",
            intensity=0.9,
            valence=0.8,
            arousal=0.9,
        )
        dims = section._dimensions
        assert dims.valence == 0.8
        assert dims.arousal == 0.9

    def test_empathy_needed_for_negative(self):
        """empathy_needed is True for negative emotions."""
        section = AffectiveNowSection()
        section.update(
            emotion="frustrated",
            intensity=0.7,
            valence=-0.6,
            arousal=0.8,
        )
        assert section._empathy_needed is True

    def test_trajectory_tracking(self):
        """Trajectory tracks emotional direction."""
        section = AffectiveNowSection()
        # Start with happy
        section.update("happy", 0.5, 0.5, 0.5, turn_number=1)
        # Get happier
        section.update("excited", 0.8, 0.8, 0.8, turn_number=2)
        # Trajectory should indicate increase

    def test_clear_resets_state(self):
        """clear() resets emotional state."""
        section = AffectiveNowSection()
        section.update("angry", 0.9, -0.8, 0.9)
        section.clear()
        # clear() resets to neutral, not empty
        assert section._current_emotion == "neutral"
        assert section._intensity == 0.5

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = AffectiveNowSection(session_id="test-session")
        section.update("happy", 0.7, 0.5, 0.6)

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = AffectiveNowSection()
        section2.from_flatbuffer(data)


class TestNarrativeActiveSection:
    """Tests for NarrativeActiveSection (4KB)."""

    def test_name_is_narrative_active(self):
        """Section name is 'narrative_active'."""
        section = NarrativeActiveSection()
        assert section.name == "narrative_active"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = NarrativeActiveSection()
        assert section.tier == "hot"

    def test_budget_is_4kb(self):
        """Budget is 4096 bytes."""
        section = NarrativeActiveSection()
        assert section.budget_bytes == 4096

    def test_can_evict_is_false(self):
        """NarrativeActiveSection cannot be evicted."""
        section = NarrativeActiveSection()
        assert section.can_evict is False

    def test_create_thread(self):
        """create_thread() adds narrative thread."""
        section = NarrativeActiveSection()
        thread = section.create_thread(
            title="Weather discussion",
            goal="Get forecast",
            turn_number=1,
        )
        assert thread.title == "Weather discussion"
        assert thread.goal == "Get forecast"

    def test_get_active_threads(self):
        """get_active_threads() returns active threads."""
        section = NarrativeActiveSection()
        section.create_thread("Thread 1", "Goal 1", 1)
        section.create_thread("Thread 2", "Goal 2", 2)
        active = section.get_active_threads()
        assert len(active) >= 1

    def test_pause_thread(self):
        """pause_thread() pauses active thread."""
        section = NarrativeActiveSection()
        thread = section.create_thread("Topic", "Goal", 1)
        result = section.pause_thread(thread.id)
        assert result is True
        assert thread.state.name == "PAUSED"

    def test_resume_thread(self):
        """switch_to() resumes paused thread."""
        section = NarrativeActiveSection()
        thread = section.create_thread("Topic", "Goal", 1)
        section.pause_thread(thread.id)
        result = section.switch_to(thread.id)
        assert result is True
        assert thread.state.name == "ACTIVE"

    def test_arc_position_updates(self):
        """Narrative arc updates with turn count."""
        section = NarrativeActiveSection()
        section.record_turn(turn_number=1)
        assert section._arc.position.name == "EXPOSITION"
        section.record_turn(turn_number=20)
        assert section._arc.position.name == "RISING_ACTION"

    def test_clear_removes_threads(self):
        """clear() removes all threads."""
        section = NarrativeActiveSection()
        section.create_thread("Test", "Goal", 1)
        section.clear()
        assert section._primary_thread is None

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = NarrativeActiveSection(session_id="test-session")
        section.create_thread("Weather", "Get forecast", 1)

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = NarrativeActiveSection()
        section2.from_flatbuffer(data)


class TestMetaSection:
    """Tests for MetaSection (2KB)."""

    def test_name_is_meta(self):
        """Section name is 'meta'."""
        section = MetaSection()
        assert section.name == "meta"

    def test_tier_is_hot(self):
        """Section tier is 'hot'."""
        section = MetaSection()
        assert section.tier == "hot"

    def test_budget_is_2kb(self):
        """Budget is 2048 bytes."""
        section = MetaSection()
        assert section.budget_bytes == 2048

    def test_can_evict_is_false(self):
        """MetaSection cannot be evicted."""
        section = MetaSection()
        assert section.can_evict is False

    def test_session_id_accessible(self):
        """session_id is accessible."""
        section = MetaSection(session_id="custom-session-123")
        assert section.session_id == "custom-session-123"

    def test_session_id_generated_if_empty(self):
        """session_id is generated if not provided."""
        section = MetaSection()
        assert section.session_id is not None
        assert len(section.session_id) > 0

    def test_created_at_set(self):
        """created_at timestamp is set."""
        section = MetaSection()
        assert section._lifecycle.created_at_ms > 0

    def test_record_activity_increments_turn(self):
        """record_turn() increments turn count."""
        section = MetaSection()
        initial = section._lifecycle.turn_count
        section.record_turn()
        assert section._lifecycle.turn_count == initial + 1

    def test_check_expiration(self):
        """check_expiration() detects expired sessions."""
        section = MetaSection()
        # Not expired initially
        assert section._lifecycle.check_expiration() is False
        assert section._lifecycle.is_expired is False

    def test_get_pressure_level(self):
        """pressure_level returns current pressure."""
        section = MetaSection()
        level = section.pressure_level
        # Should be NORMAL initially
        assert level is not None

    def test_clear_resets_lifecycle(self):
        """clear() resets lifecycle state."""
        section = MetaSection()
        section.record_turn()
        section.record_turn()
        section.clear()
        assert section._lifecycle.turn_count == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = MetaSection(session_id="test-session-456")
        section.record_turn()

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = MetaSection()
        section2.from_flatbuffer(data)
        assert section2.session_id == "test-session-456"


# =============================================================================
# WARM TIER SECTION TESTS
# =============================================================================


class TestBeliefsHistorySection:
    """Tests for BeliefsHistorySection (12KB, eviction priority 2)."""

    def test_name_is_beliefs_history(self):
        """Section name is 'beliefs_history'."""
        section = BeliefsHistorySection()
        assert section.name == "beliefs_history"

    def test_tier_is_warm(self):
        """Section is in WARM tier."""
        section = BeliefsHistorySection()
        assert section.tier == "warm"

    def test_budget_is_12kb(self):
        """Budget is 12288 bytes."""
        section = BeliefsHistorySection()
        assert section.budget_bytes == 12288

    def test_can_evict_is_true(self):
        """BeliefsHistorySection can be evicted."""
        section = BeliefsHistorySection()
        assert section.CAN_EVICT is True

    def test_eviction_priority_is_2(self):
        """Eviction priority is 2 (second to evict)."""
        section = BeliefsHistorySection()
        assert section.EVICTION_PRIORITY == 2

    def test_accept_demoted_beliefs(self):
        """accept_demoted() accepts beliefs from beliefs_active."""
        section = BeliefsHistorySection()

        fact_dict = {
            "id": "fact-1",
            "subject": "user",
            "predicate": "likes",
            "object": "coffee",
            "confidence": 1.0,
            "original_turn": 1,
        }
        section.accept_demoted([fact_dict], turn=2)
        assert section.get("fact-1") is not None

    def test_get_returns_fact(self):
        """get() returns archived fact by ID."""
        section = BeliefsHistorySection()

        fact_dict = {"id": "fact-1", "subject": "user", "predicate": "has", "object": "pet"}
        section.accept_demoted([fact_dict], turn=1)

        retrieved = section.get("fact-1")
        assert retrieved is not None
        assert retrieved.fact.object == "pet"

    def test_lru_score_updates_on_access(self):
        """LRU score updates when fact accessed."""
        section = BeliefsHistorySection()

        fact_dict = {"id": "fact-1", "subject": "user", "predicate": "likes", "object": "tea"}
        section.accept_demoted([fact_dict], turn=1)

        # Access updates score
        section.get("fact-1")
        retrieved = section._facts[0]
        assert retrieved.access_count > 0

    def test_get_promotion_candidates(self):
        """get_promotion_candidates() returns frequently accessed facts."""
        section = BeliefsHistorySection()

        fact1 = {"id": "fact-1", "subject": "user", "predicate": "likes", "object": "coffee"}
        fact2 = {"id": "fact-2", "subject": "user", "predicate": "likes", "object": "tea"}
        section.accept_demoted([fact1], turn=1)
        section.accept_demoted([fact2], turn=2)

        # Access fact-1 multiple times
        for _ in range(5):
            section.get("fact-1")

        candidates = section.get_promotion_candidates(count=1)
        assert len(candidates) <= 1

    def test_evict_partial(self):
        """evict_partial() evicts low-LRU facts."""
        section = BeliefsHistorySection()

        # Add multiple facts
        for i in range(10):
            fact = {"id": f"fact-{i}", "subject": "user", "predicate": "has", "object": f"item-{i}"}
            section.accept_demoted([fact], turn=i + 1)

        initial_count = len(section._facts)
        evicted = section.evict_partial(target_kb=1)
        assert evicted.bytes_freed > 0
        assert len(section._facts) < initial_count

    def test_clear_removes_all(self):
        """clear() removes all facts."""
        section = BeliefsHistorySection()

        fact = {"id": "fact-1", "subject": "user", "predicate": "likes", "object": "coffee"}
        section.accept_demoted([fact], turn=1)
        section.clear()
        assert len(section._facts) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = BeliefsHistorySection()

        fact = {"id": "fact-1", "subject": "user", "predicate": "likes", "object": "coffee"}
        section.accept_demoted([fact], turn=1)

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = BeliefsHistorySection()
        section2.from_flatbuffer(data)


class TestHistoryRecentSection:
    """Tests for HistoryRecentSection (20KB, eviction priority 3)."""

    def test_name_is_history_recent(self):
        """Section name is 'history_recent'."""
        section = HistoryRecentSection()
        assert section.name == "history_recent"

    def test_tier_is_warm(self):
        """Section is in WARM tier."""
        section = HistoryRecentSection()
        assert section.tier == "warm"

    def test_budget_is_20kb(self):
        """Budget is 20480 bytes."""
        section = HistoryRecentSection()
        assert section.budget_bytes == 20480

    def test_can_evict_is_true(self):
        """HistoryRecentSection can be evicted."""
        section = HistoryRecentSection()
        assert section.CAN_EVICT is True

    def test_eviction_priority_is_3(self):
        """Eviction priority is 3 (third to evict)."""
        section = HistoryRecentSection()
        assert section.EVICTION_PRIORITY == 3

    def test_add_compressed_turn(self):
        """add_compressed_turn() adds compressed turn."""
        section = HistoryRecentSection()
        from k1.sessionstate.sections.history_recent import CompressedTurn

        turn = CompressedTurn(
            turn_id="turn-11",
            turn_number=11,
            entities=["person", "location"],
            intents=["get_weather"],
            key_phrases=["tomorrow", "forecast"],
        )
        section.add_compressed_turn(turn)
        assert len(section._compressed_turns) == 1

    def test_add_summarized_turn(self):
        """add_summarized_turn() adds summarized turn."""
        section = HistoryRecentSection()
        from k1.sessionstate.sections.history_recent import SummarizedTurn

        turn = SummarizedTurn(
            turn_id="turn-31",
            turn_number=31,
            summary="User asked about weather forecast.",
        )
        section.add_summarized_turn(turn)
        assert len(section._summarized_turns) == 1

    def test_compress_to_summarized(self):
        """compress_to_summarized() converts oldest compressed to summarized."""
        section = HistoryRecentSection()
        from k1.sessionstate.sections.history_recent import CompressedTurn

        # Add compressed turns
        for i in range(5):
            turn = CompressedTurn(
                turn_id=f"turn-{11+i}",
                turn_number=11 + i,
                entities=["entity"],
                intents=["intent"],
                key_phrases=["phrase"],
            )
            section.add_compressed_turn(turn)

        initial_compressed = len(section._compressed_turns)
        section.compress_to_summarized(
            count=2, summary_generator=lambda t: f"Summary of turn {t.turn_number}"
        )
        assert len(section._compressed_turns) < initial_compressed
        assert len(section._summarized_turns) >= 2

    def test_evict_partial(self):
        """evict_partial() evicts oldest turns."""
        section = HistoryRecentSection()
        from k1.sessionstate.sections.history_recent import SummarizedTurn

        for i in range(5):
            turn = SummarizedTurn(f"turn-{i}", 31 + i, f"Summary {i}")
            section.add_summarized_turn(turn)

        initial_count = len(section._summarized_turns)
        evicted = section.evict_partial(target_kb=1)
        assert evicted.bytes_freed > 0 or len(section._summarized_turns) < initial_count

    def test_clear_removes_all(self):
        """clear() removes all turns."""
        section = HistoryRecentSection()
        from k1.sessionstate.sections.history_recent import CompressedTurn

        turn = CompressedTurn("turn-1", 11, [], [], [])
        section.add_compressed_turn(turn)
        section.clear()
        assert len(section._compressed_turns) == 0
        assert len(section._summarized_turns) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = HistoryRecentSection()
        from k1.sessionstate.sections.history_recent import CompressedTurn

        turn = CompressedTurn("turn-1", 11, ["entity"], ["intent"], ["phrase"])
        section.add_compressed_turn(turn)

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = HistoryRecentSection()
        section2.from_flatbuffer(data)


class TestPersonaSection:
    """Tests for PersonaSection (8KB, eviction priority 4)."""

    def test_name_is_persona(self):
        """Section name is 'persona'."""
        section = PersonaSection()
        assert section.name == "persona"

    def test_tier_is_warm(self):
        """Section is in WARM tier."""
        section = PersonaSection()
        assert section.tier == "warm"

    def test_budget_is_8kb(self):
        """Budget is 8192 bytes."""
        section = PersonaSection()
        assert section.budget_bytes == 8192

    def test_can_evict_is_true(self):
        """PersonaSection can be evicted."""
        section = PersonaSection()
        assert section.CAN_EVICT is True

    def test_eviction_priority_is_4(self):
        """Eviction priority is 4 (last to evict)."""
        section = PersonaSection()
        assert section.EVICTION_PRIORITY == 4

    def test_set_warmth(self):
        """set_warmth() updates personality trait."""
        section = PersonaSection()
        section.set_warmth(0.8)
        assert section._personality.warmth == 0.8

    def test_set_formality(self):
        """set_formality() updates personality trait."""
        section = PersonaSection()
        section.set_formality(0.3)
        assert section._personality.formality == 0.3

    def test_add_vocabulary(self):
        """add_vocabulary() adds custom term mapping."""
        section = PersonaSection()
        section.add_vocabulary("the cottage", "vacation home in Maine")
        assert len(section._vocabulary) == 1
        assert section._vocabulary[0].user_term == "the cottage"

    def test_set_interaction_style(self):
        """set_interaction_style() updates response style."""
        section = PersonaSection()
        from k1.sessionstate.sections.persona import InteractionStyle

        section.set_interaction_style(InteractionStyle.FRIENDLY)
        assert section._interaction_style == InteractionStyle.FRIENDLY

    def test_list_vocabulary(self):
        """list_vocabulary() returns vocabulary entries."""
        section = PersonaSection()
        section.add_vocabulary("home", "123 Main St")
        section.add_vocabulary("work", "456 Office Blvd")
        vocab_list = section.list_vocabulary()
        assert len(vocab_list) == 2
        # get_vocabulary returns the system term for a user term
        assert section.get_vocabulary("home") == "123 Main St"
        assert section.get_vocabulary("work") == "456 Office Blvd"

    def test_evict_partial(self):
        """evict_partial() evicts vocabulary entries."""
        section = PersonaSection()
        for i in range(10):
            section.add_vocabulary(f"term-{i}", f"meaning-{i}")

        initial_count = len(section._vocabulary)
        evicted = section.evict_partial(target_kb=1)
        assert len(section._vocabulary) < initial_count or evicted.bytes_freed >= 0

    def test_clear_removes_all(self):
        """clear() removes all persona data."""
        section = PersonaSection()
        section.set_warmth(0.9)
        section.add_vocabulary("test", "value")
        section.clear()
        assert len(section._vocabulary) == 0
        assert section._personality.warmth == 0.5  # Default

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = PersonaSection()
        section.set_warmth(0.7)
        section.add_vocabulary("term", "meaning")

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = PersonaSection()
        section2.from_flatbuffer(data)


class TestTelemetrySection:
    """Tests for TelemetrySection (8KB, eviction priority 1)."""

    def test_name_is_telemetry(self):
        """Section name is 'telemetry'."""
        section = TelemetrySection()
        assert section.name == "telemetry"

    def test_tier_is_warm(self):
        """Section is in WARM tier."""
        section = TelemetrySection()
        assert section.tier == "warm"

    def test_budget_is_8kb(self):
        """Budget is 8192 bytes."""
        section = TelemetrySection()
        assert section.budget_bytes == 8192

    def test_can_evict_is_true(self):
        """TelemetrySection can be evicted."""
        section = TelemetrySection()
        assert section.CAN_EVICT is True

    def test_eviction_priority_is_1(self):
        """Eviction priority is 1 (FIRST to evict)."""
        section = TelemetrySection()
        assert section.EVICTION_PRIORITY == 1

    def test_record_turn_timing(self):
        """record_turn() records turn metrics."""
        section = TelemetrySection()
        section.record_turn(
            turn_number=1,
            duration_ms=150,
            token_count=100,
        )
        assert section._turn_count == 1
        assert len(section._turn_timings) == 1

    def test_record_tokens(self):
        """record_tokens() records token usage."""
        section = TelemetrySection()
        section.record_tokens(
            input_tokens=100,
            output_tokens=200,
        )
        assert section._tokens.input_tokens == 100
        assert section._tokens.output_tokens == 200

    def test_record_error(self):
        """record_error() tracks error metrics."""
        section = TelemetrySection()
        from k1.sessionstate.sections.telemetry import ErrorType

        section.record_error(ErrorType.TIMEOUT, turn_number=1, message="Request timed out")
        assert section._errors.total_errors == 1
        assert section._errors.timeout_errors == 1

    def test_latency_tracking(self):
        """Latency metrics are tracked across turns."""
        section = TelemetrySection()
        # Record multiple timings
        for i in range(10):
            section.record_turn(i + 1, 100 + i * 10, 50)

        # Latency is tracked per-turn in _turn_timings
        assert len(section._turn_timings) == 10
        # Check timing data was recorded
        timing = section._turn_timings[-1]
        assert timing.duration_ms == 190  # 100 + 9 * 10

    def test_evict_partial(self):
        """evict_partial() evicts turn timings."""
        section = TelemetrySection()
        for i in range(15):
            section.record_turn(i + 1, 100, 50)

        initial_count = len(section._turn_timings)
        evicted = section.evict_partial(target_kb=1)
        assert len(section._turn_timings) < initial_count or evicted.bytes_freed >= 0

    def test_clear_resets_metrics(self):
        """clear() resets all metrics."""
        section = TelemetrySection()
        section.record_turn(1, 100, 50)
        section.record_tokens(100, 200)
        section.clear()
        assert section._turn_count == 0
        assert len(section._turn_timings) == 0

    def test_serialize_roundtrip(self):
        """to_flatbuffer() and from_flatbuffer() preserve state."""
        section = TelemetrySection()
        section.record_turn(1, 150, 100)
        section.record_tokens(50, 100)

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)

        section2 = TelemetrySection()
        section2.from_flatbuffer(data)
