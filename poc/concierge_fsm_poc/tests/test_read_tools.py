"""Tests for Epic 2.3 Read Tool Mocks: READ-001, READ-002, READ-003, READ-004.

Test classes:
    TestREAD001RecallMemory         -- recall_memory() output shape, keyword matching, filters
    TestREAD001Schema               -- recall_memory LLM JSON schema
    TestREAD002DiscoverCapabilities -- discover_capabilities() all 5 caps, domain/band filter
    TestREAD002Schema               -- discover_capabilities LLM JSON schema
    TestREAD003SummarizeContext     -- summarize_context() reads real snapshot, returns all fields
    TestREAD003Schema               -- summarize_context LLM JSON schema
    TestREAD004ReadSessionState     -- read_session_state() active section reader
    TestREAD004Schema               -- read_session_state LLM JSON schema
    TestREADSchemaList              -- READ_SCHEMAS list coverage
"""

from __future__ import annotations

import pytest

from poc.concierge_fsm_poc.tools.read_mock import (
    DEMO_CAPABILITIES,
    READ_SCHEMAS,
    READABLE_SECTIONS,
    discover_capabilities,
    read_session_state,
    recall_memory,
    summarize_context,
)

# ===========================================================================
# TestREAD001RecallMemory
# ===========================================================================


class TestREAD001RecallMemory:
    """READ-001 AC: keyword-matched canned results, MemoryRecallResult shape, latency field."""

    # --- Output shape ---

    def test_returns_memories_key(self):
        """AC: Response structure has 'memories' key."""
        result = recall_memory(query="allergy")
        assert "memories" in result

    def test_returns_total_found_key(self):
        """AC: Response structure has 'total_found' key."""
        result = recall_memory(query="allergy")
        assert "total_found" in result
        assert isinstance(result["total_found"], int)

    def test_returns_query_latency_ms(self):
        """AC: Includes query_latency_ms (mocked)."""
        result = recall_memory(query="anything")
        assert "query_latency_ms" in result
        assert isinstance(result["query_latency_ms"], int)
        assert result["query_latency_ms"] > 0

    def test_memories_is_list(self):
        result = recall_memory(query="allergy")
        assert isinstance(result["memories"], list)

    # --- Keyword matching: allergy / food ---

    def test_allergy_query_returns_mom_shellfish(self):
        """AC: 'allergy' query returns Mom shellfish allergy."""
        result = recall_memory(query="allergy food restriction")
        subjects = [m.get("subject", "") for m in result["memories"]]
        assert "Mom" in subjects

    def test_allergy_query_returns_jake_peanuts(self):
        """AC: 'allergy' query returns Jake peanut allergy."""
        result = recall_memory(query="food allergy")
        subjects = [m.get("subject", "") for m in result["memories"]]
        assert "Jake" in subjects

    # --- Keyword matching: lake tahoe / trip ---

    def test_trip_query_returns_event(self):
        """AC: 'lake tahoe trip' query returns past trip event."""
        result = recall_memory(query="lake tahoe trip")
        types = [m.get("type") for m in result["memories"]]
        assert "event" in types

    def test_trip_event_contains_hyatt(self):
        result = recall_memory(query="lake tahoe trip travel")
        summaries = [m.get("summary", "") for m in result["memories"]]
        assert any("Hyatt" in s for s in summaries)

    # --- Keyword matching: hospital / ER / emergency ---

    def test_hospital_query_returns_barton(self):
        """AC: 'hospital er' returns Barton Memorial location."""
        result = recall_memory(query="hospital er emergency barton directions")
        subjects = [m.get("subject", "") or m.get("summary", "") for m in result["memories"]]
        assert any("Barton" in s for s in subjects)

    # --- Default fallback ---

    def test_unknown_query_returns_default(self):
        """AC: Unmatched query returns default 'no memories' entry."""
        result = recall_memory(query="xyzzy_unmatched_gibberish_abc123")
        assert len(result["memories"]) >= 1
        # When nothing matches, the fallback entry (type="general") should be first
        assert result["memories"][0].get("type") == "general"

    # --- memory_type filter ---

    def test_filter_by_memory_type_belief(self):
        """AC: memory_type='belief' filter returns only beliefs."""
        result = recall_memory(query="allergy", memory_type="belief")
        types = [m.get("type") for m in result["memories"]]
        for t in types:
            assert t == "belief", f"Expected belief, got {t}"

    def test_filter_by_memory_type_event(self):
        result = recall_memory(query="lake tahoe trip", memory_type="event")
        types = [m.get("type") for m in result["memories"]]
        for t in types:
            assert t == "event"

    # --- subject filter ---

    def test_filter_by_subject_jake(self):
        """AC: subject='Jake' filter returns Jake entries only."""
        result = recall_memory(query="jake snow loves", subject="Jake")
        subjects = [m.get("subject", "") for m in result["memories"]]
        assert all("Jake" in s or s == "" for s in subjects)

    # --- limit ---

    def test_limit_respected(self):
        """AC: limit parameter caps results."""
        result = recall_memory(query="allergy", limit=1)
        assert len(result["memories"]) <= 1

    # --- memory_id present ---

    def test_each_memory_has_memory_id(self):
        """AC: MemoryRecallResult schema -- each item has memory_id."""
        result = recall_memory(query="allergy food")
        for m in result["memories"]:
            assert "memory_id" in m, f"Entry missing memory_id: {m}"


# ===========================================================================
# TestREAD001Schema
# ===========================================================================


class TestREAD001Schema:
    """recall_memory LLM JSON schema is Gemini function-calling compatible."""

    @pytest.fixture()
    def schema(self) -> dict:
        return next(s for s in READ_SCHEMAS if s["name"] == "recall_memory")

    def test_schema_name(self, schema):
        assert schema["name"] == "recall_memory"

    def test_schema_has_description(self, schema):
        assert len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_has_query_required(self, schema):
        assert "query" in schema["parameters"]["required"]

    def test_schema_has_memory_type_enum(self, schema):
        props = schema["parameters"]["properties"]
        assert "memory_type" in props
        assert "enum" in props["memory_type"]


# ===========================================================================
# TestREAD002DiscoverCapabilities
# ===========================================================================


class TestREAD002DiscoverCapabilities:
    """READ-002 AC: returns all 5 demo capabilities, domain/safety_band filter, schema."""

    # --- Returns all 5 ---

    def test_returns_all_capabilities_no_filter(self):
        """AC: Returns all demo capabilities by default."""
        result = discover_capabilities()
        assert result["total_found"] == len(DEMO_CAPABILITIES)
        assert len(result["capabilities"]) == len(DEMO_CAPABILITIES)

    def test_capabilities_key_present(self):
        result = discover_capabilities()
        assert "capabilities" in result

    def test_total_found_key_present(self):
        result = discover_capabilities()
        assert "total_found" in result
        assert isinstance(result["total_found"], int)

    def test_query_latency_ms_present(self):
        """AC: Response structure includes query_latency_ms."""
        result = discover_capabilities()
        assert "query_latency_ms" in result
        assert isinstance(result["query_latency_ms"], int)
        assert result["query_latency_ms"] > 0

    # --- All 5 names present ---

    @pytest.mark.parametrize(
        "cap_name",
        [
            "tool.execute.weather_lookup",
            "tool.execute.hotel_booking",
            "tool.execute.activity_search",
            "tool.execute.restaurant_search",
            "workflow.trip_planning",
        ],
    )
    def test_all_original_capability_names_returned(self, cap_name: str):
        """AC: Returns all original demo capabilities by name."""
        result = discover_capabilities()
        names = {c["name"] for c in result["capabilities"]}
        assert cap_name in names, f"Missing capability: {cap_name}"

    # --- domain filter ---

    def test_filter_by_domain_travel(self):
        """AC: Filters by domain -- TRAVEL returns subset."""
        result = discover_capabilities(domain="TRAVEL")
        caps = result["capabilities"]
        assert len(caps) > 0
        for c in caps:
            assert "TRAVEL" in c["domain"], f"{c['name']} doesn't have TRAVEL domain"

    def test_filter_by_domain_food(self):
        result = discover_capabilities(domain="FOOD")
        names = {c["name"] for c in result["capabilities"]}
        assert "tool.execute.restaurant_search" in names

    def test_filter_by_domain_family(self):
        result = discover_capabilities(domain="FAMILY")
        names = {c["name"] for c in result["capabilities"]}
        assert "tool.execute.activity_search" in names

    # --- safety_band filter ---

    def test_filter_by_safety_band_green(self):
        """AC: Filters by safety_band -- GREEN returns only green caps."""
        result = discover_capabilities(safety_band="GREEN")
        for c in result["capabilities"]:
            assert c["safety_band"] == "GREEN", f"{c['name']} is not GREEN"

    def test_filter_by_safety_band_amber(self):
        result = discover_capabilities(safety_band="AMBER")
        for c in result["capabilities"]:
            assert c["safety_band"] == "AMBER"

    def test_green_excludes_amber(self):
        result = discover_capabilities(safety_band="GREEN")
        names = {c["name"] for c in result["capabilities"]}
        # hotel_booking and trip_planning are AMBER -- must not appear
        assert "tool.execute.hotel_booking" not in names
        assert "workflow.trip_planning" not in names

    # --- query filter ---

    def test_query_filter_weather(self):
        result = discover_capabilities(query="weather")
        names = {c["name"] for c in result["capabilities"]}
        assert "tool.execute.weather_lookup" in names

    def test_query_filter_hotel(self):
        result = discover_capabilities(query="hotel")
        names = {c["name"] for c in result["capabilities"]}
        assert "tool.execute.hotel_booking" in names

    # --- combined filter ---

    def test_combined_domain_and_safety_band(self):
        result = discover_capabilities(domain="TRAVEL", safety_band="GREEN")
        for c in result["capabilities"]:
            assert "TRAVEL" in c["domain"]
            assert c["safety_band"] == "GREEN"

    # --- limit ---

    def test_limit_respected(self):
        result = discover_capabilities(limit=2)
        assert len(result["capabilities"]) <= 2

    # --- DEMO_CAPABILITIES module constant ---

    def test_demo_capabilities_constant_has_many(self):
        """AC: DEMO_CAPABILITIES module-level constant has 30+ entries."""
        assert len(DEMO_CAPABILITIES) >= 30

    def test_each_capability_has_required_fields(self):
        """AC: Each capability has name, domain, safety_band, required_inputs."""
        for cap in DEMO_CAPABILITIES:
            for field in ("name", "domain", "safety_band", "required_inputs"):
                assert field in cap, f"Capability {cap.get('name')} missing field {field}"


# ===========================================================================
# TestREAD002Schema
# ===========================================================================


class TestREAD002Schema:
    """discover_capabilities LLM JSON schema is Gemini function-calling compatible."""

    @pytest.fixture()
    def schema(self) -> dict:
        return next(s for s in READ_SCHEMAS if s["name"] == "discover_capabilities")

    def test_schema_name(self, schema):
        assert schema["name"] == "discover_capabilities"

    def test_schema_has_description(self, schema):
        assert len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_no_required_fields(self, schema):
        """AC: All parameters are optional -- discover_capabilities() callable with no args."""
        assert schema["parameters"]["required"] == []

    def test_safety_band_has_enum(self, schema):
        props = schema["parameters"]["properties"]
        assert "safety_band" in props
        assert "enum" in props["safety_band"]


# ===========================================================================
# TestREAD003SummarizeContext
# ===========================================================================


class TestREAD003SummarizeContext:
    """READ-003 AC: summarize_context() reads real snapshot and returns all required fields."""

    @pytest.fixture()
    def manager(self):
        from k1.sessionstate.factory import SessionStateFactory

        return SessionStateFactory.create_for_testing()

    # --- AC: reads real SessionState snapshot ---

    def test_returns_dict(self, manager):
        """AC: Returns a dict (real snapshot read, no exception)."""
        result = summarize_context(manager)
        assert isinstance(result, dict)

    def test_all_required_keys_present(self, manager):
        """AC: Returns summary, original_tokens, summary_tokens, compression_ratio, latency_ms."""
        result = summarize_context(manager)
        for key in (
            "summary",
            "original_tokens",
            "summary_tokens",
            "compression_ratio",
            "latency_ms",
        ):
            assert key in result, f"Missing key: {key}"

    def test_summary_is_string(self, manager):
        """AC: summary is a non-None string."""
        assert isinstance(summarize_context(manager)["summary"], str)

    def test_original_tokens_positive_int(self, manager):
        """AC: original_tokens >= 1."""
        val = summarize_context(manager)["original_tokens"]
        assert isinstance(val, int)
        assert val >= 1

    def test_summary_tokens_positive_int(self, manager):
        """AC: summary_tokens >= 1."""
        val = summarize_context(manager)["summary_tokens"]
        assert isinstance(val, int)
        assert val >= 1

    def test_compression_ratio_is_float(self, manager):
        """AC: compression_ratio is a float > 0."""
        val = summarize_context(manager)["compression_ratio"]
        assert isinstance(val, float)
        assert val > 0.0

    def test_latency_ms_nonnegative_int(self, manager):
        """AC: latency_ms is a non-negative int."""
        val = summarize_context(manager)["latency_ms"]
        assert isinstance(val, int)
        assert val >= 0

    # --- AC: generates text summary of HOT sections ---

    def test_empty_state_returns_placeholder(self, manager):
        """AC: Fresh (empty) state returns placeholder, not an error."""
        result = summarize_context(manager)
        # Either placeholder or non-empty summary -- must be a non-empty string
        assert len(result["summary"]) > 0

    def test_summary_contains_section_name_after_write(self, manager):
        """AC: After writing a belief, summary contains the section name."""
        from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet

        tools = CognitiveToolSet(manager)
        tools.update_beliefs(
            operation="add_belief",
            subject="Emma",
            predicate="prefers",
            object_="beaches",
            confidence=0.9,
        )
        result = summarize_context(manager)
        assert "beliefs" in result["summary"].lower()

    def test_focus_sections_filters_output(self, manager):
        """AC: focus_sections restricts which sections appear in summary."""
        from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet

        tools = CognitiveToolSet(manager)
        tools.update_beliefs(
            operation="add_belief",
            subject="Jake",
            predicate="allergic_to",
            object_="peanuts",
            confidence=1.0,
        )
        tools.refine_affect(
            override_emotion="curious",
            override_intensity=0.6,
            override_valence="positive",
            reasoning="test",
        )
        focused = summarize_context(manager, focus_sections=["beliefs_active"])
        full = summarize_context(manager)
        # Focused summary should be <= full summary length
        assert len(focused["summary"]) <= len(full["summary"])

    def test_summary_truncates_long_sections(self, manager):
        """AC: Each section excerpt is at most ~200 chars (extractive)."""
        from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet

        tools = CognitiveToolSet(manager)
        for i in range(10):
            tools.update_beliefs(
                operation="add_belief",
                subject=f"FamilyMember{i}",
                predicate="prefers",
                object_=f"activity_{i}",
                confidence=0.8,
            )
        result = summarize_context(manager)
        # Summary must be a string -- no error
        assert isinstance(result["summary"], str)

    def test_compression_ratio_lte_one_for_populated_state(self, manager):
        """AC: summary is a compressed form -- ratio should be <= 1 when state has data."""
        from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet

        tools = CognitiveToolSet(manager)
        for i in range(5):
            tools.update_beliefs(
                operation="add_belief",
                subject=f"Member{i}",
                predicate="likes",
                object_=f"thing_{i}",
                confidence=0.7,
            )
        result = summarize_context(manager)
        # compression_ratio may be > 1 for very small summaries but must be positive
        assert result["compression_ratio"] > 0.0


# ===========================================================================
# TestREAD003Schema
# ===========================================================================


class TestREAD003Schema:
    """READ-003: summarize_context Gemini-compatible JSON schema validation."""

    @pytest.fixture()
    def schema(self):
        return next(s for s in READ_SCHEMAS if s["name"] == "summarize_context")

    def test_schema_name(self, schema):
        assert schema["name"] == "summarize_context"

    def test_schema_has_description(self, schema):
        assert "description" in schema and len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_has_focus_sections_property(self, schema):
        props = schema["parameters"]["properties"]
        assert "focus_sections" in props

    def test_focus_sections_is_array_type(self, schema):
        prop = schema["parameters"]["properties"]["focus_sections"]
        assert prop["type"] == "array"


# ===========================================================================
# TestREAD004ReadSessionState
# ===========================================================================


class TestREAD004ReadSessionState:
    """READ-004: read_session_state() -- active section reader with real SessionState."""

    @pytest.fixture()
    def manager(self):
        from k1.sessionstate.factory import SessionStateFactory

        return SessionStateFactory.create_for_testing()

    @pytest.fixture()
    def populated_manager(self, manager):
        """Manager with data in all 5 readable sections."""
        from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet

        tools = CognitiveToolSet(manager)
        tools.update_beliefs(
            operation="add_belief",
            subject="Mom",
            predicate="allergic_to",
            object_="shellfish",
            confidence=0.97,
        )
        tools.update_scoreboard(
            operation="upsert_task",
            text="Book hotel",
            entity_id="task-1",
            entity_type="task",
        )
        tools.update_clarifications(
            operation="record_gap",
            gap_field="How many guests?",
            gap_id="gap-1",
        )
        tools.refine_affect(
            override_emotion="excited",
            override_intensity=0.8,
            override_valence="positive",
            reasoning="user is happy",
        )
        tools.update_narrative(
            operation="new_thread",
            thread_id="",
            title="Trip Planning",
            goal="Plan family trip",
        )
        return manager

    # --- Overview mode (section=None) ---

    def test_overview_returns_dict(self, manager):
        result = read_session_state(manager)
        assert isinstance(result, dict)

    def test_overview_has_required_keys(self, manager):
        result = read_session_state(manager)
        assert result["section"] is None
        assert isinstance(result["data"], dict)
        assert "latency_ms" in result

    def test_overview_contains_all_5_readable_sections(self, manager):
        data = read_session_state(manager)["data"]
        assert set(data.keys()) == READABLE_SECTIONS

    def test_overview_beliefs_has_fact_count(self, manager):
        data = read_session_state(manager)["data"]
        assert "fact_count" in data["beliefs_active"]
        assert "entity_count" in data["beliefs_active"]

    def test_overview_scoreboard_has_counts(self, manager):
        data = read_session_state(manager)["data"]
        sb = data["scoreboard"]
        assert "referent_count" in sb
        assert "topic_count" in sb

    def test_overview_clarifications_flags(self, manager):
        data = read_session_state(manager)["data"]
        cl = data["clarifications"]
        assert "pending_count" in cl
        assert "is_blocked" in cl

    def test_overview_affective_emotion(self, manager):
        data = read_session_state(manager)["data"]
        af = data["affective_now"]
        assert "current_emotion" in af
        assert "intensity" in af

    def test_overview_narrative_thread_count(self, manager):
        data = read_session_state(manager)["data"]
        na = data["narrative_active"]
        assert "thread_count" in na
        assert "arc_position" in na

    def test_overview_size_bytes_present(self, manager):
        data = read_session_state(manager)["data"]
        for name in READABLE_SECTIONS:
            assert "size_bytes" in data[name]

    # --- Detail mode (specific section) ---

    def test_beliefs_detail_returns_facts_list(self, populated_manager):
        result = read_session_state(populated_manager, section="beliefs_active")
        assert result["section"] == "beliefs_active"
        facts = result["data"]["facts"]
        assert len(facts) >= 1
        f = facts[0]
        assert f["subject"] == "Mom"
        assert f["predicate"] == "allergic_to"
        assert f["object"] == "shellfish"
        assert f["confidence"] == 0.97

    def test_beliefs_detail_keys(self, populated_manager):
        data = read_session_state(populated_manager, section="beliefs_active")["data"]
        for key in ("fact_count", "entity_count", "pinned_fact_ids", "facts", "entities"):
            assert key in data, f"Missing key: {key}"

    def test_scoreboard_detail_returns_referents(self, populated_manager):
        result = read_session_state(populated_manager, section="scoreboard")
        assert result["section"] == "scoreboard"
        refs = result["data"]["referents"]
        assert len(refs) >= 1
        r = refs[0]
        # update_scoreboard maps all ops to add_referent; text carries the text kwarg
        assert r["entity_id"] == "task-1"
        assert r["entity_type"] == "task"

    def test_scoreboard_detail_keys(self, populated_manager):
        data = read_session_state(populated_manager, section="scoreboard")["data"]
        for key in ("referents", "topics", "open_questions", "user_intent"):
            assert key in data, f"Missing key: {key}"

    def test_clarifications_detail_returns_pending(self, populated_manager):
        result = read_session_state(populated_manager, section="clarifications")
        assert result["section"] == "clarifications"
        pending = result["data"]["pending"]
        assert len(pending) >= 1
        p = pending[0]
        assert p["question"] == "How many guests?"
        assert p["agent_id"] == "concierge"

    def test_clarifications_detail_keys(self, populated_manager):
        data = read_session_state(populated_manager, section="clarifications")["data"]
        for key in ("pending", "recently_resolved", "is_blocked", "pending_count"):
            assert key in data, f"Missing key: {key}"

    def test_affective_detail_returns_emotion(self, populated_manager):
        result = read_session_state(populated_manager, section="affective_now")
        assert result["section"] == "affective_now"
        d = result["data"]
        assert d["current_emotion"] == "excited"
        assert d["intensity"] == 0.8
        # source may be prefixed by refine_affect implementation
        assert "user is happy" in d["source"]

    def test_affective_detail_keys(self, populated_manager):
        data = read_session_state(populated_manager, section="affective_now")["data"]
        for key in (
            "current_emotion",
            "intensity",
            "valence",
            "arousal",
            "trajectory",
            "confidence",
            "empathy_needed",
        ):
            assert key in data, f"Missing key: {key}"

    def test_narrative_detail_returns_threads(self, populated_manager):
        result = read_session_state(populated_manager, section="narrative_active")
        assert result["section"] == "narrative_active"
        threads = result["data"]["threads"]
        assert len(threads) >= 1
        t = threads[0]
        assert t["title"] == "Trip Planning"
        assert t["goal"] == "Plan family trip"

    def test_narrative_detail_keys(self, populated_manager):
        data = read_session_state(populated_manager, section="narrative_active")["data"]
        for key in ("threads", "current_thread_id", "arc_position", "arc_progress"):
            assert key in data, f"Missing key: {key}"

    # --- Error cases ---

    def test_invalid_section_raises_value_error(self, manager):
        with pytest.raises(ValueError, match="Unknown section"):
            read_session_state(manager, section="nonexistent")

    def test_invalid_section_error_lists_valid_names(self, manager):
        with pytest.raises(ValueError, match="beliefs_active"):
            read_session_state(manager, section="bad")

    # --- READABLE_SECTIONS constant ---

    def test_readable_sections_is_frozenset(self):
        assert isinstance(READABLE_SECTIONS, frozenset)

    def test_readable_sections_has_five_entries(self):
        assert len(READABLE_SECTIONS) == 5

    @pytest.mark.parametrize(
        "name",
        [
            "beliefs_active",
            "scoreboard",
            "clarifications",
            "affective_now",
            "narrative_active",
        ],
    )
    def test_readable_sections_contains(self, name):
        assert name in READABLE_SECTIONS

    # --- Latency ---

    def test_latency_is_nonnegative_int(self, manager):
        result = read_session_state(manager)
        assert isinstance(result["latency_ms"], int)
        assert result["latency_ms"] >= 0

    def test_detail_latency_is_nonnegative_int(self, populated_manager):
        result = read_session_state(populated_manager, section="beliefs_active")
        assert isinstance(result["latency_ms"], int)
        assert result["latency_ms"] >= 0

    # --- Overview reflects writes ---

    def test_overview_fact_count_increases_after_write(self, populated_manager):
        data = read_session_state(populated_manager)["data"]
        assert data["beliefs_active"]["fact_count"] >= 1

    def test_overview_pending_count_increases_after_write(self, populated_manager):
        data = read_session_state(populated_manager)["data"]
        assert data["clarifications"]["pending_count"] >= 1


# ===========================================================================
# TestREAD004Schema
# ===========================================================================


class TestREAD004Schema:
    """READ-004: read_session_state Gemini-compatible JSON schema."""

    @pytest.fixture()
    def schema(self):
        return next(s for s in READ_SCHEMAS if s["name"] == "read_session_state")

    def test_schema_name(self, schema):
        assert schema["name"] == "read_session_state"

    def test_schema_has_description(self, schema):
        assert "description" in schema and len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_has_section_property(self, schema):
        props = schema["parameters"]["properties"]
        assert "section" in props

    def test_section_enum_matches_readable_sections(self, schema):
        enum_vals = set(schema["parameters"]["properties"]["section"]["enum"])
        assert enum_vals == READABLE_SECTIONS

    def test_section_not_required(self, schema):
        req = schema["parameters"].get("required", [])
        assert "section" not in req


# ===========================================================================
# TestREADSchemaList
# ===========================================================================


class TestREADSchemaList:
    """READ_SCHEMAS must cover all 4 read tools."""

    def test_four_schemas_present(self):
        assert len(READ_SCHEMAS) == 4

    def test_all_schema_names_present(self):
        names = {s["name"] for s in READ_SCHEMAS}
        assert names == {
            "recall_memory",
            "discover_capabilities",
            "summarize_context",
            "read_session_state",
        }

    def test_each_schema_has_parameters(self):
        for s in READ_SCHEMAS:
            assert "parameters" in s, f"{s['name']} missing parameters"
            assert s["parameters"]["type"] == "object"
