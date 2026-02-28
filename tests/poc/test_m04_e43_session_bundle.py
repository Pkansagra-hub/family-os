"""
tests.poc.test_m04_e43_session_bundle -- E4.3 Session Bundle Tool.

Validates the 3 issues of Epic 4.3:
  4.3.1 -- update_session_bundle tool with idempotency_key
  4.3.2 -- Bundle wired through writer_port.batch_mutations
  4.3.3 -- stop_on_rejection semantics with partial rollback info

Test count target: ~20 tests.
"""

from __future__ import annotations

from poc.k1_poc.sessionstate.factory import SessionStateFactory
from poc.k1_poc.tools.implementations import (
    TOOL_REGISTRY,
    ToolContext,
    execute_update_session_bundle,
)
from poc.k1_poc.tools.schemas_front import FRONT_TOOL_SCHEMAS, UPDATE_SESSION_BUNDLE_SCHEMA

# =========================================================================
# Helpers
# =========================================================================


def _make_ss():
    """Create a real SessionStateManager for testing."""
    ss = SessionStateFactory.create_for_testing()
    ss.start()
    return ss


def _make_writer(ss):
    """Create a DirectWriterAdapter wired to the given manager."""
    from poc.k1_poc.sessionstate.adapters.direct_writer import DirectWriterAdapter

    return DirectWriterAdapter(manager=ss, guard=ss._mutation_guard)


def _make_ctx(ss, writer):
    """Build a ToolContext with writer_port wired."""
    return ToolContext(
        session_manager=ss,
        cognitive_trace_id="trace-e43-test",
        actor="front",
        writer_port=writer,
    )


# =========================================================================
# 4.3.1 -- update_session_bundle tool registration and basic behavior
# =========================================================================


class TestBundleToolRegistration:
    """update_session_bundle is registered and discoverable (M4 4.3.1)."""

    def test_registered_in_tool_registry(self) -> None:
        """Tool appears in TOOL_REGISTRY."""
        assert "update_session_bundle" in TOOL_REGISTRY

    def test_schema_exists(self) -> None:
        """UPDATE_SESSION_BUNDLE_SCHEMA is defined."""
        assert UPDATE_SESSION_BUNDLE_SCHEMA.name == "update_session_bundle"

    def test_schema_in_front_tool_schemas(self) -> None:
        """Schema is included in FRONT_TOOL_SCHEMAS list."""
        names = [s.name for s in FRONT_TOOL_SCHEMAS]
        assert "update_session_bundle" in names

    def test_schema_front_tool_count(self) -> None:
        """FRONT_TOOL_SCHEMAS now has 10 schemas (9 original + 1 bundle)."""
        assert len(FRONT_TOOL_SCHEMAS) == 10

    def test_schema_is_cognitive_category(self) -> None:
        """Bundle tool is in the cognitive category."""
        assert UPDATE_SESSION_BUNDLE_SCHEMA.category == "cognitive"

    def test_schema_has_side_effects(self) -> None:
        """Bundle tool has side_effects=True."""
        assert UPDATE_SESSION_BUNDLE_SCHEMA.side_effects is True


class TestBundleEmptyInput:
    """Bundle tool rejects empty or invalid input (M4 4.3.1)."""

    def test_empty_mutations_returns_error(self) -> None:
        """Empty mutations array returns error."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)
        result = execute_update_session_bundle({"mutations": []}, ctx)
        assert result.status == "error"
        assert "required" in result.error

    def test_missing_mutations_returns_error(self) -> None:
        """No mutations key returns error."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)
        result = execute_update_session_bundle({}, ctx)
        assert result.status == "error"

    def test_mutation_missing_section_returns_error(self) -> None:
        """Mutation without section key returns error."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)
        result = execute_update_session_bundle(
            {"mutations": [{"operation": "add_fact", "data": {}}]},
            ctx,
        )
        assert result.status == "error"
        assert "section" in result.error

    def test_mutation_missing_operation_returns_error(self) -> None:
        """Mutation without operation key returns error."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)
        result = execute_update_session_bundle(
            {"mutations": [{"section": "beliefs_active", "data": {}}]},
            ctx,
        )
        assert result.status == "error"
        assert "operation" in result.error


# =========================================================================
# 4.3.1 -- Idempotency key behavior
# =========================================================================


class TestBundleIdempotency:
    """Idempotency key prevents duplicate application (M4 4.3.1)."""

    def test_idempotency_key_caches_result(self) -> None:
        """Calling with same key twice returns cached result, no re-apply."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "user",
                        "predicate": "likes",
                        "obj": "coffee",
                        "confidence": 0.9,
                        "source": "test",
                    },
                },
            ],
            "idempotency_key": "key-abc-001",
        }

        result1 = execute_update_session_bundle(args, ctx)
        assert result1.status == "ok"
        assert result1.data["applied"] == 1

        # Second call with same key -- cached, no re-apply
        result2 = execute_update_session_bundle(args, ctx)
        assert result2 is result1  # Exact same object returned

        # Verify only 1 fact was added (not 2)
        beliefs = ss.get_section("beliefs_active")
        facts = beliefs.find_by_subject("user")
        assert len(facts) == 1

    def test_different_keys_both_apply(self) -> None:
        """Different idempotency keys apply independently."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        base_args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "user",
                        "predicate": "likes",
                        "obj": "tea",
                        "confidence": 0.9,
                        "source": "test",
                    },
                },
            ],
        }

        args1 = {**base_args, "idempotency_key": "key-001"}
        args2 = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "user",
                        "predicate": "likes",
                        "obj": "water",
                        "confidence": 0.7,
                        "source": "test",
                    },
                },
            ],
            "idempotency_key": "key-002",
        }

        r1 = execute_update_session_bundle(args1, ctx)
        r2 = execute_update_session_bundle(args2, ctx)
        assert r1.status == "ok"
        assert r2.status == "ok"

        beliefs = ss.get_section("beliefs_active")
        facts = beliefs.find_by_subject("user")
        assert len(facts) == 2

    def test_no_idempotency_key_always_applies(self) -> None:
        """Without idempotency_key, every call applies."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "trip",
                        "predicate": "to",
                        "obj": "Paris",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
            ],
        }

        r1 = execute_update_session_bundle(args, ctx)
        r2 = execute_update_session_bundle(args, ctx)
        assert r1.status == "ok"
        assert r2.status == "ok"

        beliefs = ss.get_section("beliefs_active")
        facts = beliefs.find_by_subject("trip")
        assert len(facts) == 2  # Both applied


# =========================================================================
# 4.3.2 -- Wiring through writer_port.batch_mutations
# =========================================================================


class TestBundleBatchWiring:
    """Bundle tool uses batch_mutations for all writes (M4 4.3.2)."""

    def test_three_mutations_all_applied(self) -> None:
        """Batch of 3 mutations to LLM-writable sections, all applied."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "hotel",
                        "predicate": "is",
                        "obj": "booked",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
                {
                    "section": "scoreboard",
                    "operation": "push_question",
                    "data": {"text": "Which dates?", "asked_by": "user"},
                },
                {
                    "section": "narrative_active",
                    "operation": "create_thread",
                    "data": {
                        "title": "hotel_booking",
                        "goal": "Book a hotel",
                        "auto_switch": True,
                    },
                },
            ],
            "idempotency_key": "batch-3-test",
        }

        result = execute_update_session_bundle(args, ctx)
        assert result.status == "ok"
        assert result.data["applied"] == 3
        assert result.data["rejected"] == 0
        assert result.data["cancelled"] == 0
        assert result.data["stopped_early"] is False
        assert len(result.data["details"]) == 3

        # Verify each section was actually mutated
        beliefs = ss.get_section("beliefs_active")
        assert len(beliefs.find_by_subject("hotel")) == 1

        scoreboard = ss.get_section("scoreboard")
        assert len(scoreboard._qud_stack) >= 1

        narrative = ss.get_section("narrative_active")
        assert narrative._primary_thread is not None
        assert narrative._primary_thread.title == "hotel_booking"

    def test_batch_rejects_system_owned_section(self) -> None:
        """Batch with a system-owned section mutation is rejected (E4.2.4 guard)."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "x",
                        "predicate": "y",
                        "obj": "z",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
                {
                    "section": "control",
                    "operation": "update",
                    "data": {"fsm_state": "HACKED"},
                },
            ],
            "idempotency_key": "batch-reject-test",
            "stop_on_rejection": True,
        }

        result = execute_update_session_bundle(args, ctx)
        # First mutation applied, second rejected, none cancelled (it was last)
        assert result.data["applied"] == 1
        assert result.data["rejected"] == 1
        assert result.status == "partial"

    def test_details_contain_per_mutation_status(self) -> None:
        """Each detail entry has section, status, and reason."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "a",
                        "predicate": "b",
                        "obj": "c",
                        "confidence": 0.5,
                        "source": "test",
                    },
                },
            ],
            "idempotency_key": "details-test",
        }

        result = execute_update_session_bundle(args, ctx)
        details = result.data["details"]
        assert len(details) == 1
        assert details[0]["section"] == "beliefs_active"
        assert details[0]["status"] == "applied"


# =========================================================================
# 4.3.3 -- stop_on_rejection semantics
# =========================================================================


class TestBundleStopOnRejection:
    """stop_on_rejection controls batch abort behavior (M4 4.3.3)."""

    def test_stop_on_rejection_true_cancels_remaining(self) -> None:
        """With stop_on_rejection=True, 2nd rejected cancels 3rd."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "ok1",
                        "predicate": "is",
                        "obj": "fine",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
                {
                    "section": "control",  # system-owned -> rejected
                    "operation": "update",
                    "data": {},
                },
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "ok2",
                        "predicate": "is",
                        "obj": "also_fine",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
            ],
            "idempotency_key": "stop-true-test",
            "stop_on_rejection": True,
        }

        result = execute_update_session_bundle(args, ctx)
        assert result.data["applied"] == 1
        assert result.data["rejected"] == 1
        assert result.data["cancelled"] == 1
        assert result.data["stopped_early"] is True
        assert result.status == "partial"

        # Verify 3rd mutation was NOT applied
        beliefs = ss.get_section("beliefs_active")
        assert len(beliefs.find_by_subject("ok2")) == 0
        # But 1st was
        assert len(beliefs.find_by_subject("ok1")) == 1

        # Verify details
        details = result.data["details"]
        assert details[0]["status"] == "applied"
        assert details[1]["status"] == "rejected"
        assert details[2]["status"] == "cancelled"

    def test_stop_on_rejection_false_continues(self) -> None:
        """With stop_on_rejection=False, 2nd rejected but 3rd still applied."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "pass1",
                        "predicate": "is",
                        "obj": "ok",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
                {
                    "section": "task_state",  # system-owned -> rejected
                    "operation": "update",
                    "data": {},
                },
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "pass3",
                        "predicate": "is",
                        "obj": "also_ok",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
            ],
            "idempotency_key": "stop-false-test",
            "stop_on_rejection": False,
        }

        result = execute_update_session_bundle(args, ctx)
        assert result.data["applied"] == 2
        assert result.data["rejected"] == 1
        assert result.data["cancelled"] == 0
        assert result.data["stopped_early"] is False
        assert result.status == "partial"

        # Verify 1st and 3rd were applied
        beliefs = ss.get_section("beliefs_active")
        assert len(beliefs.find_by_subject("pass1")) == 1
        assert len(beliefs.find_by_subject("pass3")) == 1

        # Verify details
        details = result.data["details"]
        assert details[0]["status"] == "applied"
        assert details[1]["status"] == "rejected"
        assert details[2]["status"] == "applied"

    def test_all_rejected_returns_error_status(self) -> None:
        """When all mutations are rejected, status is 'error'."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "control",
                    "operation": "update",
                    "data": {},
                },
                {
                    "section": "meta",
                    "operation": "set",
                    "data": {},
                },
            ],
            "idempotency_key": "all-rejected-test",
            "stop_on_rejection": False,
        }

        result = execute_update_session_bundle(args, ctx)
        assert result.status == "error"
        assert result.data["applied"] == 0

    def test_all_applied_returns_ok_status(self) -> None:
        """When all mutations succeed, status is 'ok'."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        args = {
            "mutations": [
                {
                    "section": "beliefs_active",
                    "operation": "add_fact",
                    "data": {
                        "subject": "allok",
                        "predicate": "test",
                        "obj": "yes",
                        "confidence": 1.0,
                        "source": "test",
                    },
                },
            ],
            "idempotency_key": "all-ok-test",
        }

        result = execute_update_session_bundle(args, ctx)
        assert result.status == "ok"
        assert result.data["applied"] == 1
        assert result.data["stopped_early"] is False
