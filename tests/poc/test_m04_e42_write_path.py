"""
tests.poc.test_m04_e42_write_path -- E4.2 Write Path Enforcement.

Validates the 4 issues of Epic 4.2:
  4.2.1 -- writer_port field on ToolContext
  4.2.2 -- LLM-writable allowlist in config
  4.2.3 -- 6 cognitive tools route writes through writer_port
  4.2.4 -- Runtime guard rejects LLM writes to system-owned sections

Test count target: ~35 tests.
"""

from __future__ import annotations

from poc.k1_poc.config import get_config, reset_config
from poc.k1_poc.sessionstate.factory import SessionStateFactory
from poc.k1_poc.sessionstate.ports.writer import MutationRequest, RejectionCategory
from poc.k1_poc.tools.implementations import (
    ToolContext,
    execute_promote_belief,
    execute_refine_affect,
    execute_update_beliefs,
    execute_update_clarifications,
    execute_update_narrative,
    execute_update_scoreboard,
)

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
        cognitive_trace_id="trace-e42-test",
        actor="front",
        writer_port=writer,
    )


# =========================================================================
# 4.2.1 -- writer_port on ToolContext
# =========================================================================


class TestToolContextWriterPort:
    """ToolContext exposes writer_port field (M4 4.2.1)."""

    def test_writer_port_default_is_none(self) -> None:
        """Without explicit assignment, writer_port is None."""
        ss = _make_ss()
        ctx = ToolContext(session_manager=ss)
        assert ctx.writer_port is None

    def test_writer_port_assignable(self) -> None:
        """writer_port can be set to a real IWriterPort."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = ToolContext(session_manager=ss, writer_port=writer)
        assert ctx.writer_port is writer

    def test_writer_port_is_connected(self) -> None:
        """writer_port.is_connected is True after bootstrap."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = ToolContext(session_manager=ss, writer_port=writer)
        assert ctx.writer_port.is_connected


# =========================================================================
# 4.2.2 -- LLM-writable allowlist in config
# =========================================================================


class TestLlmWritableConfig:
    """Config exposes llm_writable_sections + system_owned_sections."""

    def setup_method(self) -> None:
        reset_config()

    def test_llm_writable_sections_present(self) -> None:
        """get_config().sessionstate.llm_writable_sections returns 5 sections."""
        cfg = get_config()
        assert len(cfg.sessionstate.llm_writable_sections) == 5

    def test_llm_writable_sections_content(self) -> None:
        """The 5 LLM-writable sections are the correct ones."""
        expected = {
            "beliefs_active",
            "scoreboard",
            "clarifications",
            "narrative_active",
            "affective_now",
        }
        cfg = get_config()
        assert set(cfg.sessionstate.llm_writable_sections) == expected

    def test_system_owned_sections_present(self) -> None:
        """get_config().sessionstate.system_owned_sections returns 10 sections."""
        cfg = get_config()
        assert len(cfg.sessionstate.system_owned_sections) == 10

    def test_system_owned_sections_content(self) -> None:
        """The 10 system-owned sections are correct."""
        expected = {
            "control",
            "task_state",
            "task_artifacts",
            "meta",
            "history_active",
            "beliefs_history",
            "history_recent",
            "persona",
            "telemetry",
            "artifacts_warm",
        }
        cfg = get_config()
        assert set(cfg.sessionstate.system_owned_sections) == expected

    def test_allowlist_plus_system_equals_all_sections(self) -> None:
        """LLM-writable + system-owned = ALL 15 sections (no gaps)."""
        from poc.k1_poc.sessionstate.sizetracker import ALL_SECTIONS

        cfg = get_config()
        combined = set(cfg.sessionstate.llm_writable_sections) | set(
            cfg.sessionstate.system_owned_sections
        )
        assert combined == ALL_SECTIONS

    def test_no_overlap_between_writable_and_system(self) -> None:
        """No section appears in both lists."""
        cfg = get_config()
        overlap = set(cfg.sessionstate.llm_writable_sections) & set(
            cfg.sessionstate.system_owned_sections
        )
        assert overlap == set()


# =========================================================================
# 4.2.3 -- Cognitive tools route writes through writer_port
# =========================================================================


class TestUpdateBeliefsWritePath:
    """update_beliefs routes writes through writer_port."""

    def test_add_fact_via_writer_port(self) -> None:
        """New belief creates MutationRequest routed through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_beliefs(
            {
                "beliefs": [
                    {"subject": "Alice", "predicate": "likes", "object": "cats", "confidence": 0.9}
                ]
            },
            ctx,
        )
        assert result.status == "ok"
        assert result.data["stored"] == 1

        # Verify the fact landed in the real section
        beliefs = ss.get_section("beliefs_active")
        facts = beliefs.find_by_subject("Alice")
        assert len(facts) == 1
        assert facts[0].confidence == 0.9

    def test_update_existing_belief_via_writer_port(self) -> None:
        """Updating confidence of existing belief routes through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        # First call: add
        execute_update_beliefs(
            {
                "beliefs": [
                    {"subject": "Bob", "predicate": "has", "object": "dog", "confidence": 0.5}
                ]
            },
            ctx,
        )
        # Second call: update (same SPO)
        result = execute_update_beliefs(
            {
                "beliefs": [
                    {"subject": "Bob", "predicate": "has", "object": "dog", "confidence": 0.95}
                ]
            },
            ctx,
        )
        assert result.status == "ok"
        assert result.data["updated"] == 1

        beliefs = ss.get_section("beliefs_active")
        facts = beliefs.find_by_subject("Bob")
        assert facts[0].confidence == 0.95

    def test_empty_beliefs_returns_error(self) -> None:
        """Empty beliefs array returns error without touching writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_beliefs({"beliefs": []}, ctx)
        assert result.status == "error"


class TestUpdateScoreboardWritePath:
    """update_scoreboard routes sub-actions through writer_port."""

    def test_push_question_via_writer_port(self) -> None:
        """push_question creates MutationRequest for scoreboard."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_scoreboard({"qud_push": "What is your name?"}, ctx)
        assert result.status == "ok"
        assert result.data["qud_depth"] == 1

    def test_add_referent_via_writer_port(self) -> None:
        """referent_updates routes each referent through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_scoreboard({"referent_updates": {"he": "entity-bob"}}, ctx)
        assert result.status == "ok"
        assert result.data["active_referents"] == 1

    def test_topic_shift_via_writer_port(self) -> None:
        """topic_shift routes through writer_port."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_scoreboard({"topic_shift": "weather"}, ctx)
        assert result.status == "ok"

    def test_combined_scoreboard_ops(self) -> None:
        """Multiple ops in one call all route through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_scoreboard(
            {
                "qud_push": "Where to eat?",
                "referent_updates": {"there": "entity-restaurant"},
                "topic_shift": "dining",
            },
            ctx,
        )
        assert result.status == "ok"
        assert result.data["qud_depth"] >= 1


class TestUpdateClarificationsWritePath:
    """update_clarifications routes writes through writer_port."""

    def test_add_gap_via_writer_port(self) -> None:
        """New clarification gap is created through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_clarifications(
            {"gaps": [{"field": "destination", "question": "Where to?", "severity": "blocking"}]},
            ctx,
        )
        assert result.status == "ok"
        assert result.data["open_gaps"] == 1
        assert result.data["blocking_gaps"] == 1

    def test_resolve_gap_via_writer_port(self) -> None:
        """Resolving a gap routes the answer through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        # Add then resolve
        execute_update_clarifications(
            {"gaps": [{"field": "date", "question": "When?", "severity": "helpful"}]},
            ctx,
        )
        result = execute_update_clarifications({"resolved_gaps": ["date"]}, ctx)
        assert result.status == "ok"
        assert result.data["open_gaps"] == 0


class TestUpdateNarrativeWritePath:
    """update_narrative routes writes through writer_port."""

    def test_switch_creates_thread_via_writer(self) -> None:
        """switch action on non-existent thread creates via writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_narrative(
            {"action": "switch", "thread_id": "topic-weather", "summary": "Discuss weather"},
            ctx,
        )
        assert result.status == "ok"
        assert result.data["total_threads"] >= 1

    def test_close_thread_via_writer(self) -> None:
        """close action resolves thread through writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        # Create thread first
        execute_update_narrative(
            {"action": "switch", "thread_id": "t1", "summary": "Initial"},
            ctx,
        )
        # Now get the real thread ID (create_thread assigns UUID)
        narrative = ss.get_section("narrative_active")
        narrative.get_thread("t1")
        # If thread_id="t1" was used as title, we need the actual ID
        # The apply() create_thread returns the id, but our tool uses
        # thread_id as title. Let's get the primary thread's ID
        primary = narrative._primary_thread
        assert primary is not None

        result = execute_update_narrative(
            {"action": "close", "thread_id": primary.id},
            ctx,
        )
        assert result.status == "ok"

    def test_missing_action_returns_error(self) -> None:
        """Missing action or thread_id returns error."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_update_narrative({"action": "", "thread_id": ""}, ctx)
        assert result.status == "error"


class TestRefineAffectWritePath:
    """refine_affect routes writes through writer_port."""

    def test_update_affect_via_writer(self) -> None:
        """Affect update routes through writer_port."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_refine_affect(
            {"emotion": "joy", "valence": 0.8, "arousal": 0.6, "confidence": 0.9},
            ctx,
        )
        assert result.status == "ok"
        assert result.data["updated"] is True

    def test_missing_fields_returns_error(self) -> None:
        """Missing required fields returns error without touching writer."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_refine_affect({"emotion": "joy"}, ctx)
        assert result.status == "error"


class TestPromoteBeliefWritePath:
    """promote_belief routes writes through writer_port."""

    def test_promote_via_writer(self) -> None:
        """Confidence update routes through writer_port."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        # First create a belief
        execute_update_beliefs(
            {
                "beliefs": [
                    {
                        "subject": "User",
                        "predicate": "prefers",
                        "object": "dark mode",
                        "confidence": 0.4,
                    }
                ]
            },
            ctx,
        )
        beliefs = ss.get_section("beliefs_active")
        facts = beliefs.find_by_subject("User")
        fact_id = facts[0].id

        result = execute_promote_belief({"belief_id": fact_id, "new_confidence": 0.95}, ctx)
        assert result.status == "ok"
        assert result.data["promoted"] is True
        assert result.data["from_tier"] == "COLD"

        # Verify confidence updated in real section
        updated = beliefs.get_fact(fact_id)
        assert updated.confidence == 0.95

    def test_promote_nonexistent_returns_error(self) -> None:
        """Promoting a non-existent belief returns error."""
        ss = _make_ss()
        writer = _make_writer(ss)
        ctx = _make_ctx(ss, writer)

        result = execute_promote_belief({"belief_id": "nonexistent", "new_confidence": 0.9}, ctx)
        assert result.status == "error"


# =========================================================================
# 4.2.4 -- Runtime guard rejecting LLM writes to system-owned sections
# =========================================================================


class TestRuntimeSectionGuard:
    """DirectWriterAdapter rejects tool: prefixed writers for system sections."""

    def test_tool_write_to_beliefs_active_allowed(self) -> None:
        """tool:front writing to beliefs_active is allowed."""
        ss = _make_ss()
        writer = _make_writer(ss)

        req = MutationRequest.create(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": "X",
                "predicate": "is",
                "obj": "Y",
                "confidence": 1.0,
                "source": "test",
            },
            writer_id="tool:front",
            cognitive_trace_id="trace-guard-test",
        )
        resp = writer.request_mutation(req)
        assert resp.approved

    def test_tool_write_to_control_rejected(self) -> None:
        """tool:front writing to control is rejected (system-owned)."""
        ss = _make_ss()
        writer = _make_writer(ss)

        req = MutationRequest.create(
            section="control",
            operation="set",
            data={"key": "value"},
            writer_id="tool:front",
            cognitive_trace_id="trace-guard-test",
        )
        resp = writer.request_mutation(req)
        assert not resp.approved
        assert resp.rejection_category == RejectionCategory.AUTHORIZATION
        assert "system-owned" in resp.reason

    def test_tool_write_to_task_state_rejected(self) -> None:
        """tool:back writing to task_state is rejected."""
        ss = _make_ss()
        writer = _make_writer(ss)

        req = MutationRequest.create(
            section="task_state",
            operation="set",
            data={},
            writer_id="tool:back",
            cognitive_trace_id="trace-guard-test",
        )
        resp = writer.request_mutation(req)
        assert not resp.approved
        assert resp.rejection_category == RejectionCategory.AUTHORIZATION

    def test_tool_write_to_meta_rejected(self) -> None:
        """tool:front writing to meta is rejected."""
        ss = _make_ss()
        writer = _make_writer(ss)

        req = MutationRequest.create(
            section="meta",
            operation="set",
            data={},
            writer_id="tool:front",
            cognitive_trace_id="trace-guard-test",
        )
        resp = writer.request_mutation(req)
        assert not resp.approved
        assert resp.rejection_category == RejectionCategory.AUTHORIZATION

    def test_system_writer_to_control_allowed(self) -> None:
        """Non-tool writer (fsm) writing to control is allowed."""
        ss = _make_ss()
        writer = _make_writer(ss)

        req = MutationRequest.create(
            section="control",
            operation="set",
            data={"key": "value"},
            writer_id="fsm",
            cognitive_trace_id="trace-guard-test",
        )
        resp = writer.request_mutation(req)
        assert resp.approved

    def test_tool_write_to_all_llm_writable_sections(self) -> None:
        """tool:front can write to all 5 LLM-writable sections."""
        ss = _make_ss()
        writer = _make_writer(ss)
        cfg = get_config()

        for section in cfg.sessionstate.llm_writable_sections:
            req = MutationRequest.create(
                section=section,
                operation="update",
                data={},
                writer_id="tool:front",
                cognitive_trace_id="trace-guard-test",
            )
            resp = writer.request_mutation(req)
            # Should not be rejected by the section guard
            # (may be rejected by other reasons like validation, but NOT AUTHORIZATION)
            if not resp.approved:
                assert resp.rejection_category != RejectionCategory.AUTHORIZATION, (
                    f"Section {section} should be LLM-writable but was rejected "
                    f"with AUTHORIZATION: {resp.reason}"
                )

    def test_tool_write_to_all_system_sections_rejected(self) -> None:
        """tool:front is rejected for all 10 system-owned sections."""
        ss = _make_ss()
        writer = _make_writer(ss)
        cfg = get_config()

        for section in cfg.sessionstate.system_owned_sections:
            req = MutationRequest.create(
                section=section,
                operation="set",
                data={},
                writer_id="tool:front",
                cognitive_trace_id="trace-guard-test",
            )
            resp = writer.request_mutation(req)
            assert not resp.approved, f"Section {section} should be system-owned"
            assert resp.rejection_category == RejectionCategory.AUTHORIZATION

    def test_direct_writer_to_system_section_allowed(self) -> None:
        """writer_id='direct' (non-tool) can write to system sections."""
        ss = _make_ss()
        writer = _make_writer(ss)

        req = MutationRequest.create(
            section="control",
            operation="set",
            data={"key": "value"},
            writer_id="direct",
            cognitive_trace_id="trace-guard-test",
        )
        resp = writer.request_mutation(req)
        assert resp.approved
