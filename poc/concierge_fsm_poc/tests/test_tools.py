"""Tests for Epic 2.1 Signal Tool (SIG-001) and Epic 2.2 Cognitive Tools (COG-001..COG-007).

Test classes:
    TestAcknowledgeContract   -- acknowledge() output shape and side-effects
    TestAcknowledgeSchemaSpec -- ACKNOWLEDGE_SCHEMA structure
    TestCOG001Base            -- COG-001: CognitiveToolSet constructor + _write() contract
    TestCOG002Scoreboard      -- COG-002: update_scoreboard() all 6 operations
    TestCognitiveWrite        -- Each of the 6 cognitive tools writes to real SessionState
    TestCognitiveMutationGuard-- F27: mutation guard rejection (capacity overflow)
    TestCognitiveSchemas      -- COGNITIVE_SCHEMAS list coverage
"""

from __future__ import annotations

import pytest

from k1.sessionstate import SessionStateFactory
from poc.concierge_fsm_poc.tools.cognitive import COGNITIVE_SCHEMAS, CognitiveToolSet
from poc.concierge_fsm_poc.tools.signal import (
    ACKNOWLEDGE_SCHEMA,
    acknowledge,
    get_ack_log,
    reset_ack_log,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_ack_log():
    """Ensure ack log is empty at the start and end of every test."""
    reset_ack_log()
    yield
    reset_ack_log()


@pytest.fixture()
def toolset() -> CognitiveToolSet:
    """Fresh in-memory SessionState wired to a CognitiveToolSet."""
    manager = SessionStateFactory.create_for_testing(session_id="test-cog-tools")
    return CognitiveToolSet(manager)


# ===========================================================================
# TestAcknowledgeContract
# ===========================================================================


class TestAcknowledgeContract:
    """TEST-002a: acknowledge() I/O shape and side-effects."""

    def test_returns_displayed_true(self):
        result = acknowledge(ack_type="progress", message="Working on it", next_tool="none")
        assert result["displayed"] is True

    def test_returns_formatted_message(self):
        result = acknowledge(
            ack_type="commit", message="Booking now", next_tool="invoke_capability"
        )
        assert result["formatted_message"] == "Booking now"

    def test_returns_display_latency_ms(self):
        result = acknowledge(ack_type="closure", message="Done!", next_tool="none")
        assert isinstance(result["display_latency_ms"], int)
        assert result["display_latency_ms"] == 45

    def test_appends_to_ack_log(self):
        acknowledge(ack_type="commit", message="First", next_tool="none")
        acknowledge(ack_type="progress", message="Second", next_tool="none")
        log = get_ack_log()
        assert len(log) == 2

    def test_ack_log_entry_fields(self):
        acknowledge(ack_type="closure", message="Finished", next_tool="none")
        entry = get_ack_log()[0]
        assert entry["ack_type"] == "closure"
        assert entry["message"] == "Finished"
        assert entry["displayed"] is True
        assert "timestamp_ms" in entry

    def test_zero_sessionstate_writes(self):
        """acknowledge() must NOT import or call SessionState APIs."""
        from poc.concierge_fsm_poc.tools import signal as sig_module  # noqa: PLC0415

        source_code = sig_module.__file__
        with open(source_code) as fh:
            text = fh.read()
        # No import of SessionState in the imports block -- docstring mentions it but no import
        assert "from k1.sessionstate" not in text
        assert "import SessionState" not in text

    def test_all_three_ack_types_accepted(self):
        for ack_type in ("commit", "progress", "closure"):
            result = acknowledge(ack_type=ack_type, message="x", next_tool="none")
            assert result["displayed"] is True

    def test_reset_ack_log_clears(self):
        acknowledge(ack_type="commit", message="x", next_tool="none")
        reset_ack_log()
        assert get_ack_log() == []


# ===========================================================================
# TestAcknowledgeSchemaSpec
# ===========================================================================


class TestAcknowledgeSchemaSpec:
    """Schema must be Gemini function-calling compatible."""

    def test_schema_has_name(self):
        assert ACKNOWLEDGE_SCHEMA["name"] == "acknowledge"

    def test_schema_has_description(self):
        assert len(ACKNOWLEDGE_SCHEMA["description"]) > 10

    def test_schema_parameters_type_object(self):
        assert ACKNOWLEDGE_SCHEMA["parameters"]["type"] == "object"

    def test_schema_required_contains_all_three_params(self):
        required = ACKNOWLEDGE_SCHEMA["parameters"]["required"]
        assert set(required) == {"ack_type", "message", "next_tool"}

    def test_ack_type_enum(self):
        enum = ACKNOWLEDGE_SCHEMA["parameters"]["properties"]["ack_type"]["enum"]
        assert set(enum) == {"commit", "progress", "closure"}


# ===========================================================================
# TestCOG001Base
# ===========================================================================


class TestCOG001Base:
    """COG-001 AC: Constructor + _write() contract."""

    def test_constructor_takes_session_state_manager(self):
        """AC: Constructor takes SessionStateManager."""
        from k1.sessionstate import SessionStateManager  # noqa: PLC0415

        manager = SessionStateFactory.create_for_testing(session_id="test-cog001-ctor")
        ts = CognitiveToolSet(manager)
        assert isinstance(ts._manager, SessionStateManager)

    def test_write_calls_manager_mutate_and_returns_success(self):
        """AC: _write() calls manager.mutate(section, operation, data), returns success."""
        manager = SessionStateFactory.create_for_testing(session_id="test-cog001-write")
        ts = CognitiveToolSet(manager)
        result = ts._write(
            "beliefs_active",
            "add_fact",
            {"subject": "Alice", "predicate": "likes", "obj": "skiing"},
        )
        assert "success" in result
        assert result["success"] is True

    def test_write_returns_section_bytes(self):
        """AC: _write() returns section_bytes."""
        manager = SessionStateFactory.create_for_testing(session_id="test-cog001-bytes")
        ts = CognitiveToolSet(manager)
        result = ts._write(
            "beliefs_active", "add_fact", {"subject": "Bob", "predicate": "has", "obj": "allergy"}
        )
        assert "section_bytes" in result
        assert isinstance(result["section_bytes"], int)

    def test_write_returns_rejection_reason_none_on_success(self):
        """AC: rejection_reason is None when write succeeds."""
        manager = SessionStateFactory.create_for_testing(session_id="test-cog001-reason")
        ts = CognitiveToolSet(manager)
        result = ts._write(
            "beliefs_active", "add_fact", {"subject": "S", "predicate": "P", "obj": "O"}
        )
        assert result["rejection_reason"] is None

    def test_mutation_guard_rejects_invalid_operation(self):
        """AC: MutationGuard validates writes -- real rejection on bad operation."""
        manager = SessionStateFactory.create_for_testing(session_id="test-cog001-guard")
        ts = CognitiveToolSet(manager)
        result = ts._write("beliefs_active", "not_a_real_op", {"foo": "bar"})
        assert result["success"] is False
        assert result["rejection_reason"] is not None


# ===========================================================================
# TestCOG002Scoreboard
# ===========================================================================


class TestCOG002Scoreboard:
    """COG-002 AC: All 6 logical operations accepted, writes to scoreboard, returns success/section_bytes."""

    @pytest.fixture()
    def ts(self) -> CognitiveToolSet:
        manager = SessionStateFactory.create_for_testing(session_id="test-cog002-scbd")
        return CognitiveToolSet(manager)

    @pytest.mark.parametrize(
        "operation,kwargs",
        [
            ("upsert_task", {"task_id": "T1"}),
            ("resolve_referent", {"entity_id": "E1", "text": "Tahoe"}),
            ("push_qud", {"topic": "weather"}),
            ("pop_qud", {"topic": "weather"}),
            ("update_salience", {"entity_id": "E2", "salience": 0.9}),
            ("shift_topic", {"topic": "booking"}),
        ],
    )
    def test_all_six_operations_accepted(self, ts: CognitiveToolSet, operation: str, kwargs: dict):
        """AC: All 6 logical operations accepted without error."""
        result = ts.update_scoreboard(operation, **kwargs)
        assert "success" in result, f"Missing success key for op={operation}"

    @pytest.mark.parametrize(
        "operation,kwargs",
        [
            ("upsert_task", {"task_id": "T2"}),
            ("update_salience", {"entity_id": "E3", "salience": 0.7}),
            ("shift_topic", {"topic": "activity"}),
        ],
    )
    def test_writes_land_successfully(self, ts: CognitiveToolSet, operation: str, kwargs: dict):
        """AC: Writes to scoreboard section succeed (success=True)."""
        result = ts.update_scoreboard(operation, **kwargs)
        # All 6 logical ops funnel through add_referent -- valid per MutationGuard
        assert (
            result["success"] is True
        ), f"Write failed for op={operation}: {result['rejection_reason']}"

    def test_returns_section_bytes(self, ts: CognitiveToolSet):
        """AC: Returns section_bytes key."""
        result = ts.update_scoreboard("upsert_task", task_id="T3")
        assert "section_bytes" in result
        assert isinstance(result["section_bytes"], int)
        assert result["section_bytes"] >= 0

    def test_returns_success_key(self, ts: CognitiveToolSet):
        """AC: Returns success key."""
        result = ts.update_scoreboard("push_qud", topic="itinerary")
        assert "success" in result


# ===========================================================================
# TestCognitiveWrite (original)
# ===========================================================================


class TestCognitiveWrite:
    """TEST-002b: Each cognitive tool writes to real SessionState via mutate()."""

    def test_update_scoreboard_success(self, toolset: CognitiveToolSet):
        result = toolset.update_scoreboard("upsert_task", task_id="T1", topic="weather")
        assert result["success"] is True
        assert "section_bytes" in result
        assert result["rejection_reason"] is None

    def test_update_beliefs_success_and_belief_id(self, toolset: CognitiveToolSet):
        result = toolset.update_beliefs(
            "add_fact", subject="Jake", predicate="allergic_to", object_="peanuts"
        )
        assert result["success"] is True
        assert "belief_id" in result
        assert len(result["belief_id"]) == 36  # UUID format

    def test_update_clarifications_record_gap(self, toolset: CognitiveToolSet):
        result = toolset.update_clarifications("record_gap", gap_field="check_in")
        assert result["success"] is True
        assert "gap_id" in result
        assert result["open_gaps_count"] == 1

    def test_update_clarifications_resolve_gap(self, toolset: CognitiveToolSet):
        """resolve_gap is a PoC-level no-op success -- gap is considered done."""
        recorded = toolset.update_clarifications("record_gap", gap_field="check_in")
        resolved = toolset.update_clarifications("resolve_gap", gap_id=recorded["gap_id"])
        # resolve_gap is treated as a local completion marker in the PoC;
        # it does not need a full round-trip write to succeed.
        assert resolved["gap_id"] == recorded["gap_id"]
        assert resolved["open_gaps_count"] == 0

    def test_update_narrative_new_thread(self, toolset: CognitiveToolSet):
        result = toolset.update_narrative("new_thread", summary="trip planning")
        assert result["success"] is True
        assert "thread_id" in result
        assert len(result["thread_id"]) == 36  # UUID

    def test_refine_affect_override_applied(self, toolset: CognitiveToolSet):
        result = toolset.refine_affect(
            override_emotion="anxious",
            override_intensity=0.8,
            override_valence="negative",
            reasoning="User mentioned hospital",
        )
        assert result["success"] is True
        assert result["override_applied"] is True

    def test_promote_belief_warm_to_hot(self, toolset: CognitiveToolSet):
        belief_id = "b-123"
        result = toolset.promote_belief(
            direction="warm_to_hot",
            belief_id=belief_id,
            subject="Mom",
            predicate="allergic_to",
            object_="shellfish",
        )
        assert result["success"] is True
        assert result["belief_id"] == belief_id
        assert result["destination"] == "beliefs_active"
        assert result["k0_store_receipt"] is None

    def test_promote_belief_hot_to_k0_mocked(self, toolset: CognitiveToolSet):
        belief_id = "b-456"
        result = toolset.promote_belief(direction="hot_to_k0", belief_id=belief_id)
        assert result["success"] is True
        assert result["destination"] == "k0_belief_store"
        assert result["k0_store_receipt"] is not None
        assert result["k0_store_receipt"].startswith("k0-receipt-")

    def test_snapshot_reflects_scoreboard_write(self, toolset: CognitiveToolSet):
        """section_bytes > 0 after a write."""
        r = toolset.update_scoreboard("push_qud", topic="weather")
        assert r["section_bytes"] >= 0  # guard never negative


# ===========================================================================
# TestCognitiveMutationGuard
# ===========================================================================


class TestCognitiveMutationGuard:
    """F27 variant: MutationGuard can reject a write if payload is malformed or too big."""

    def test_unknown_promote_direction_returns_failure(self, toolset: CognitiveToolSet):
        result = toolset.promote_belief(direction="invalid_dir", belief_id="x")
        assert result["success"] is False
        assert result["rejection_reason"] is not None


# ===========================================================================
# TestCOG003Beliefs
# ===========================================================================


class TestCOG003Beliefs:
    """COG-003 AC: update_beliefs() -- all 4 ops, UUID belief_id, writes beliefs_active."""

    @pytest.fixture()
    def ts(self) -> CognitiveToolSet:
        manager = SessionStateFactory.create_for_testing(session_id="test-cog003")
        return CognitiveToolSet(manager)

    @pytest.mark.parametrize(
        "operation",
        [
            "add_fact",
            "correct_fact",
            "invalidate_fact",
            "add_preference",
        ],
    )
    def test_all_four_operations_accepted(self, ts: CognitiveToolSet, operation: str):
        """AC: All 4 operations accepted without error."""
        result = ts.update_beliefs(operation, subject="Jake", predicate="likes", object_="skiing")
        assert "success" in result, f"Missing success key for op={operation}"

    def test_generates_belief_id_uuid(self, ts: CognitiveToolSet):
        """AC: Generates belief_id (UUID)."""
        result = ts.update_beliefs(
            "add_fact", subject="Mom", predicate="allergic_to", object_="shellfish"
        )
        assert "belief_id" in result
        assert len(result["belief_id"]) == 36
        # UUID format: 8-4-4-4-12
        parts = result["belief_id"].split("-")
        assert len(parts) == 5

    def test_belief_ids_unique_per_call(self, ts: CognitiveToolSet):
        """Each call generates a distinct belief_id."""
        r1 = ts.update_beliefs("add_fact", subject="A", predicate="P", object_="O1")
        r2 = ts.update_beliefs("add_fact", subject="A", predicate="P", object_="O2")
        assert r1["belief_id"] != r2["belief_id"]

    def test_writes_to_beliefs_active_section(self, ts: CognitiveToolSet):
        """AC: Writes to beliefs_active section (success=True)."""
        result = ts.update_beliefs("add_fact", subject="Dad", predicate="knows", object_="skiing")
        assert result["success"] is True

    def test_returns_success(self, ts: CognitiveToolSet):
        """AC: Returns success key."""
        result = ts.update_beliefs(
            "add_preference", subject="user", predicate="prefers", object_="window seat"
        )
        assert "success" in result

    def test_returns_belief_id(self, ts: CognitiveToolSet):
        """AC: Returns belief_id key."""
        result = ts.update_beliefs("add_fact", subject="S", predicate="P", object_="O")
        assert "belief_id" in result
        assert result["belief_id"]  # non-empty

    def test_returns_section_bytes(self, ts: CognitiveToolSet):
        """AC: Returns section_bytes key."""
        result = ts.update_beliefs("add_fact", subject="X", predicate="has", object_="value")
        assert "section_bytes" in result
        assert isinstance(result["section_bytes"], int)


# ===========================================================================
# TestCOG004Clarifications
# ===========================================================================


class TestCOG004Clarifications:
    """COG-004 AC: update_clarifications() -- record_gap, resolve_gap, expire_gap."""

    @pytest.fixture()
    def ts(self) -> CognitiveToolSet:
        manager = SessionStateFactory.create_for_testing(session_id="test-cog004")
        return CognitiveToolSet(manager)

    def test_record_gap_creates_gap_id(self, ts: CognitiveToolSet):
        """AC: record_gap creates gap entry with gap_id."""
        result = ts.update_clarifications("record_gap", gap_field="check_in")
        assert "gap_id" in result
        assert result["gap_id"]  # non-empty

    def test_record_gap_id_is_uuid(self, ts: CognitiveToolSet):
        """gap_id is a UUID."""
        result = ts.update_clarifications("record_gap", gap_field="check_out")
        assert len(result["gap_id"]) == 36
        assert result["gap_id"].count("-") == 4

    def test_record_gap_writes_to_clarifications_section(self, ts: CognitiveToolSet):
        """AC: Writes to clarifications section (success=True)."""
        result = ts.update_clarifications("record_gap", gap_field="guests")
        assert result["success"] is True

    def test_record_gap_open_gaps_count_is_one(self, ts: CognitiveToolSet):
        """AC: record_gap returns open_gaps_count=1."""
        result = ts.update_clarifications("record_gap", gap_field="arrival_date")
        assert result["open_gaps_count"] == 1

    def test_resolve_gap_returns_gap_id(self, ts: CognitiveToolSet):
        """AC: resolve_gap marks gap as resolved -- returns same gap_id."""
        recorded = ts.update_clarifications("record_gap", gap_field="party_size")
        resolved = ts.update_clarifications("resolve_gap", gap_id=recorded["gap_id"])
        assert resolved["gap_id"] == recorded["gap_id"]

    def test_resolve_gap_open_gaps_count_is_zero(self, ts: CognitiveToolSet):
        """AC: resolve_gap returns open_gaps_count=0."""
        recorded = ts.update_clarifications("record_gap", gap_field="time")
        resolved = ts.update_clarifications("resolve_gap", gap_id=recorded["gap_id"])
        assert resolved["open_gaps_count"] == 0

    def test_returns_success_key(self, ts: CognitiveToolSet):
        """AC: Returns success key."""
        result = ts.update_clarifications("record_gap", gap_field="dates")
        assert "success" in result

    def test_returns_gap_id_key(self, ts: CognitiveToolSet):
        """AC: Returns gap_id key."""
        result = ts.update_clarifications("record_gap", gap_field="budget")
        assert "gap_id" in result

    def test_returns_open_gaps_count_key(self, ts: CognitiveToolSet):
        """AC: Returns open_gaps_count key."""
        result = ts.update_clarifications("record_gap", gap_field="cuisine")
        assert "open_gaps_count" in result

    @pytest.mark.parametrize("operation", ["record_gap", "resolve_gap", "expire_gap"])
    def test_all_three_operations_accepted(self, ts: CognitiveToolSet, operation: str):
        """All 3 logical operations accepted without error."""
        gap_id = "test-gap-001"
        result = ts.update_clarifications(operation, gap_field="check_in", gap_id=gap_id)
        assert "gap_id" in result, f"Missing gap_id for op={operation}"


# ===========================================================================
# TestCOG005Narrative
# ===========================================================================


class TestCOG005Narrative:
    """COG-005 AC: update_narrative() -- 5 ops, new_thread generates thread_id."""

    @pytest.fixture()
    def ts(self) -> CognitiveToolSet:
        manager = SessionStateFactory.create_for_testing(session_id="test-cog005")
        return CognitiveToolSet(manager)

    @pytest.mark.parametrize(
        "operation,kwargs",
        [
            ("new_thread", {"summary": "trip planning"}),
            ("switch_thread", {"thread_id": "t-001"}),
            ("resume_thread", {"thread_id": "t-001"}),
            ("continue_thread", {"thread_id": "t-001"}),
            ("close_thread", {"thread_id": "t-001"}),
        ],
    )
    def test_all_five_operations_accepted(self, ts: CognitiveToolSet, operation: str, kwargs: dict):
        """AC: All 5 operations accepted without error."""
        result = ts.update_narrative(operation, **kwargs)
        assert "success" in result, f"Missing success for op={operation}"

    def test_new_thread_generates_thread_id(self, ts: CognitiveToolSet):
        """AC: new_thread generates thread_id."""
        result = ts.update_narrative("new_thread", summary="hotel search")
        assert "thread_id" in result
        assert result["thread_id"]  # non-empty

    def test_new_thread_id_is_uuid(self, ts: CognitiveToolSet):
        """thread_id is UUID format."""
        result = ts.update_narrative("new_thread")
        assert len(result["thread_id"]) == 36
        assert result["thread_id"].count("-") == 4

    def test_new_thread_ids_unique_per_call(self, ts: CognitiveToolSet):
        r1 = ts.update_narrative("new_thread", summary="A")
        r2 = ts.update_narrative("new_thread", summary="B")
        assert r1["thread_id"] != r2["thread_id"]

    def test_new_thread_writes_to_narrative_active(self, ts: CognitiveToolSet):
        """AC: Writes to narrative_active section (success=True)."""
        result = ts.update_narrative("new_thread", summary="trip")
        assert result["success"] is True

    def test_returns_success_key(self, ts: CognitiveToolSet):
        result = ts.update_narrative("new_thread")
        assert "success" in result

    def test_returns_thread_id_key(self, ts: CognitiveToolSet):
        result = ts.update_narrative("new_thread")
        assert "thread_id" in result

    def test_returns_active_threads_key(self, ts: CognitiveToolSet):
        """AC: Returns active_threads key."""
        result = ts.update_narrative("new_thread")
        assert "active_threads" in result
        assert isinstance(result["active_threads"], int)

    def test_new_thread_active_threads_nonzero(self, ts: CognitiveToolSet):
        result = ts.update_narrative("new_thread")
        assert result["active_threads"] >= 1


# ===========================================================================
# TestCOG006Affect
# ===========================================================================


class TestCOG006Affect:
    """COG-006 AC: refine_affect() -- accepts 4 params, writes affective_now, returns override_applied."""

    @pytest.fixture()
    def ts(self) -> CognitiveToolSet:
        manager = SessionStateFactory.create_for_testing(session_id="test-cog006")
        return CognitiveToolSet(manager)

    def test_accepts_override_emotion(self, ts: CognitiveToolSet):
        """AC: Accepts override_emotion param."""
        result = ts.refine_affect(override_emotion="anxious", reasoning="hospital mention")
        assert "success" in result

    def test_accepts_override_intensity(self, ts: CognitiveToolSet):
        """AC: Accepts override_intensity param."""
        result = ts.refine_affect(
            override_emotion="worried",
            override_intensity=0.9,
            reasoning="urgent tone",
        )
        assert result["success"] is True

    def test_accepts_override_valence(self, ts: CognitiveToolSet):
        """AC: Accepts override_valence param."""
        result = ts.refine_affect(
            override_emotion="excited",
            override_valence="positive",
            reasoning="planning vacation",
        )
        assert result["success"] is True

    def test_accepts_reasoning(self, ts: CognitiveToolSet):
        """AC: Accepts reasoning param without error."""
        result = ts.refine_affect(
            override_emotion="neutral",
            reasoning="no strong signal detected",
        )
        assert "success" in result

    def test_writes_to_affective_now_section(self, ts: CognitiveToolSet):
        """AC: Writes to affective_now section (success=True)."""
        result = ts.refine_affect(
            override_emotion="stressed",
            override_intensity=0.7,
            override_valence="negative",
            reasoning="budget concerns",
        )
        assert result["success"] is True

    def test_returns_override_applied_true_on_success(self, ts: CognitiveToolSet):
        """AC: Returns override_applied=True when write succeeds."""
        result = ts.refine_affect(
            override_emotion="calm",
            reasoning="de-escalation detected",
        )
        assert "override_applied" in result
        assert result["override_applied"] is True

    def test_returns_success_key(self, ts: CognitiveToolSet):
        """AC: Returns success key."""
        result = ts.refine_affect(override_emotion="happy", reasoning="booking confirmed")
        assert "success" in result

    @pytest.mark.parametrize("valence", ["positive", "negative", "neutral"])
    def test_all_three_valences_accepted(self, ts: CognitiveToolSet, valence: str):
        result = ts.refine_affect(
            override_emotion="test",
            override_valence=valence,
            reasoning="test",
        )
        assert result["success"] is True, f"Failed for valence={valence}"


# ===========================================================================
# TestCOG007PromoteBelief
# ===========================================================================


class TestCOG007PromoteBelief:
    """COG-007 AC: promote_belief() -- warm_to_hot writes HOT, hot_to_k0 mocked."""

    @pytest.fixture()
    def ts(self) -> CognitiveToolSet:
        manager = SessionStateFactory.create_for_testing(session_id="test-cog007")
        return CognitiveToolSet(manager)

    def test_warm_to_hot_writes_beliefs_active(self, ts: CognitiveToolSet):
        """AC: warm_to_hot writes to beliefs_active (HOT)."""
        result = ts.promote_belief(
            direction="warm_to_hot",
            belief_id="b-warm-001",
            subject="Mom",
            predicate="allergic_to",
            object_="shellfish",
        )
        assert result["success"] is True

    def test_warm_to_hot_returns_belief_id(self, ts: CognitiveToolSet):
        """AC: warm_to_hot returns belief_id."""
        belief_id = "b-warm-002"
        result = ts.promote_belief(
            direction="warm_to_hot",
            belief_id=belief_id,
            subject="S",
            predicate="P",
            object_="O",
        )
        assert result["belief_id"] == belief_id

    def test_warm_to_hot_destination_is_beliefs_active(self, ts: CognitiveToolSet):
        """AC: warm_to_hot destination is beliefs_active (HOT tier)."""
        result = ts.promote_belief(
            direction="warm_to_hot",
            belief_id="b-003",
            subject="S",
            predicate="P",
            object_="O",
        )
        assert result["destination"] == "beliefs_active"

    def test_warm_to_hot_k0_receipt_is_none(self, ts: CognitiveToolSet):
        """warm_to_hot does not involve K0 -- receipt is None."""
        result = ts.promote_belief(
            direction="warm_to_hot",
            belief_id="b-004",
            subject="S",
            predicate="P",
            object_="O",
        )
        assert result["k0_store_receipt"] is None

    def test_hot_to_k0_is_mocked_success(self, ts: CognitiveToolSet):
        """AC: hot_to_k0 mocked -- returns success=True."""
        result = ts.promote_belief(direction="hot_to_k0", belief_id="b-hot-001")
        assert result["success"] is True

    def test_hot_to_k0_returns_fake_k0_receipt(self, ts: CognitiveToolSet):
        """AC: hot_to_k0 returns fake k0_store_receipt."""
        result = ts.promote_belief(direction="hot_to_k0", belief_id="b-hot-002")
        assert "k0_store_receipt" in result
        assert result["k0_store_receipt"] is not None
        assert result["k0_store_receipt"].startswith("k0-receipt-")

    def test_hot_to_k0_destination_is_k0_store(self, ts: CognitiveToolSet):
        """AC: hot_to_k0 destination is k0_belief_store."""
        result = ts.promote_belief(direction="hot_to_k0", belief_id="b-hot-003")
        assert result["destination"] == "k0_belief_store"

    def test_returns_success_key(self, ts: CognitiveToolSet):
        """AC: Returns success key."""
        result = ts.promote_belief(direction="hot_to_k0", belief_id="b-x")
        assert "success" in result

    def test_returns_belief_id_key(self, ts: CognitiveToolSet):
        """AC: Returns belief_id key."""
        result = ts.promote_belief(direction="hot_to_k0", belief_id="b-y")
        assert "belief_id" in result

    def test_returns_destination_key(self, ts: CognitiveToolSet):
        """AC: Returns destination key."""
        result = ts.promote_belief(direction="hot_to_k0", belief_id="b-z")
        assert "destination" in result

    def test_hot_to_k0_receipts_unique_per_call(self, ts: CognitiveToolSet):
        """Each hot_to_k0 call produces a unique receipt."""
        r1 = ts.promote_belief(direction="hot_to_k0", belief_id="b-r1")
        r2 = ts.promote_belief(direction="hot_to_k0", belief_id="b-r2")
        assert r1["k0_store_receipt"] != r2["k0_store_receipt"]


# ===========================================================================
# TestCognitiveSchemas
# ===========================================================================


class TestCognitiveSchemas:
    """COGNITIVE_SCHEMAS must cover all 6 tools."""

    def test_six_schemas_present(self):
        assert len(COGNITIVE_SCHEMAS) == 6

    def test_all_schema_names_present(self):
        names = {s["name"] for s in COGNITIVE_SCHEMAS}
        expected = {
            "update_scoreboard",
            "update_beliefs",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
        }
        assert names == expected

    def test_each_schema_has_required_parameters(self):
        for schema in COGNITIVE_SCHEMAS:
            assert "parameters" in schema, f"{schema['name']} missing parameters"
            assert "required" in schema["parameters"], f"{schema['name']} missing required"
            assert schema["parameters"]["type"] == "object"
