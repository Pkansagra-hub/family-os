"""
Tests for ConciergeToolRegistry backed by real k1.SessionState.

Validates all 14 Concierge tools plus final_answer, including
SessionState mutations, entity resolution, and canned response data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure PoC root and project root are on sys.path
_POC_ROOT = Path(__file__).parent.parent
_PROJECT_ROOT = _POC_ROOT.parent.parent
for p in (_POC_ROOT, _PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from tools.concierge_tools import ConciergeToolRegistry, reset_session_state


@pytest.fixture(autouse=True)
def clean_session():
    """Reset SessionState before and after each test."""
    reset_session_state()
    yield
    reset_session_state()


@pytest.fixture
def registry() -> ConciergeToolRegistry:
    return ConciergeToolRegistry()


# -----------------------------------------------------------------------
# Registry basics
# -----------------------------------------------------------------------


class TestRegistryBasics:
    def test_tool_count(self, registry: ConciergeToolRegistry):
        assert len(registry.get_tool_names()) == 16  # 14 + final_answer + spawn_agent

    def test_tool_names(self, registry: ConciergeToolRegistry):
        names = set(registry.get_tool_names())
        expected = {
            "acknowledge",
            "update_scoreboard",
            "update_beliefs",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
            "resolve_entity",
            "recall_memory",
            "discover_capabilities",
            "summarize_context",
            "invoke_capability",
            "spawn_via_fabric",
            "execute_workflow",
            "final_answer",
            "spawn_agent",
        }
        assert names == expected

    def test_declarations_have_schema(self, registry: ConciergeToolRegistry):
        for decl in registry.get_tool_declarations():
            assert "name" in decl
            assert "description" in decl
            assert "parameters" in decl

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, registry: ConciergeToolRegistry):
        result = await registry.execute("nonexistent_tool", {})
        assert not result.ok
        assert result.error_code == "TOOL_NOT_FOUND"

    def test_reset_clears_state(self, registry: ConciergeToolRegistry):
        registry._ack_log.append({"test": True})
        registry._call_counts["test"] = 5
        registry.reset()
        assert len(registry._ack_log) == 0
        assert len(registry._call_counts) == 0


# -----------------------------------------------------------------------
# Signal tools
# -----------------------------------------------------------------------


class TestAcknowledge:
    @pytest.mark.asyncio
    async def test_acknowledge_commit(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "acknowledge",
            {
                "ack_type": "commit",
                "message": "I will plan a birthday dinner for your Mom.",
                "next_tool": "update_scoreboard",
            },
        )
        assert result.ok
        assert result.output["displayed"] is True
        assert "birthday dinner" in result.output["formatted_message"]
        assert len(registry._ack_log) == 1

    @pytest.mark.asyncio
    async def test_acknowledge_progress(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "acknowledge",
            {
                "ack_type": "progress",
                "message": "Working on it...",
                "next_tool": "recall_memory",
            },
        )
        assert result.ok
        assert result.output["display_latency_ms"] > 0

    @pytest.mark.asyncio
    async def test_acknowledge_closure(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "acknowledge",
            {
                "ack_type": "closure",
                "message": "All done.",
                "next_tool": "none",
            },
        )
        assert result.ok


# -----------------------------------------------------------------------
# Cognitive tools
# -----------------------------------------------------------------------


class TestUpdateScoreboard:
    @pytest.mark.asyncio
    async def test_set_task(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_scoreboard",
            {
                "operation": "set_task",
                "task_name": "plan_dinner",
                "task_status": "in_progress",
                "progress_pct": 10.0,
            },
        )
        assert result.ok
        assert result.output["success"]
        assert result.output["operation"] == "set_task"

    @pytest.mark.asyncio
    async def test_add_referent(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_scoreboard",
            {
                "operation": "add_referent",
                "referent_text": "Mom",
                "entity_id": "person_mom",
                "entity_type": "person",
            },
        )
        assert result.ok
        assert result.output["success"]

    @pytest.mark.asyncio
    async def test_push_topic(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_scoreboard",
            {"operation": "push_topic", "topic": "birthday_dinner", "salience": 0.95},
        )
        assert result.ok
        assert result.output["success"]

    @pytest.mark.asyncio
    async def test_set_intent(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_scoreboard",
            {"operation": "set_intent", "intent": "Plan a vegan birthday dinner"},
        )
        assert result.ok


class TestResolveEntity:
    @pytest.mark.asyncio
    async def test_resolve_new_entity(self, registry: ConciergeToolRegistry):
        result = await registry.execute("resolve_entity", {"name": "Mom", "entity_type": "person"})
        assert result.ok
        assert not result.output["found"]  # new entity
        assert result.output["entity_id"].startswith("person:Mom:")
        assert result.output["canonical_name"] == "Mom"
        assert result.output["entity_type"] == "person"
        assert result.output["confidence"] == 0.6

    @pytest.mark.asyncio
    async def test_resolve_existing_entity(self, registry: ConciergeToolRegistry):
        # First resolve creates referent
        r1 = await registry.execute("resolve_entity", {"name": "Jake", "entity_type": "person"})
        entity_id = r1.output["entity_id"]
        # Second resolve finds it
        r2 = await registry.execute("resolve_entity", {"name": "Jake", "entity_type": "person"})
        assert r2.ok
        assert r2.output["found"]
        assert r2.output["entity_id"] == entity_id
        assert r2.output["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_resolve_with_type_hint(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "resolve_entity", {"name": "Birthday Dinner", "entity_type": "event"}
        )
        assert result.ok
        assert result.output["entity_id"].startswith("event:Birthday Dinner:")
        assert result.output["entity_type"] == "event"

    @pytest.mark.asyncio
    async def test_resolve_empty_name_rejected(self, registry: ConciergeToolRegistry):
        result = await registry.execute("resolve_entity", {"name": ""})
        assert result.ok
        assert not result.output["found"]
        assert result.output["entity_id"] == ""


class TestUpdateBeliefs:
    @pytest.mark.asyncio
    async def test_add_fact(self, registry: ConciergeToolRegistry):
        # Resolve entity first (required by strict mode)
        r = await registry.execute("resolve_entity", {"name": "Mom", "entity_type": "person"})
        entity_id = r.output["entity_id"]

        result = await registry.execute(
            "update_beliefs",
            {
                "operation": "add_fact",
                "entity_id": entity_id,
                "predicate": "diet",
                "object_value": "vegan",
                "confidence": 0.95,
                "source": "user_stated",
            },
        )
        assert result.ok
        assert result.output["success"]
        assert result.output["belief_id"]  # non-empty
        assert result.output["entity_id"] == entity_id
        assert not result.output["is_correction"]

    @pytest.mark.asyncio
    async def test_correct_fact(self, registry: ConciergeToolRegistry):
        # Resolve entity
        r = await registry.execute("resolve_entity", {"name": "Dad", "entity_type": "person"})
        entity_id = r.output["entity_id"]

        # First add
        await registry.execute(
            "update_beliefs",
            {
                "operation": "add_fact",
                "entity_id": entity_id,
                "predicate": "allergy",
                "object_value": "peanuts",
            },
        )
        # Correct
        result = await registry.execute(
            "update_beliefs",
            {
                "operation": "correct_fact",
                "entity_id": entity_id,
                "predicate": "allergy",
                "object_value": "tree_nuts",
            },
        )
        assert result.ok
        assert result.output["is_correction"]

    @pytest.mark.asyncio
    async def test_rejects_without_entity_id(self, registry: ConciergeToolRegistry):
        """update_beliefs MUST reject raw subject names without entity_id."""
        result = await registry.execute(
            "update_beliefs",
            {
                "operation": "add_fact",
                "subject": "Mom",
                "predicate": "diet",
                "object_value": "vegan",
            },
        )
        assert result.ok  # handler returns dict, not exception
        assert not result.output["success"]
        assert "entity_id" in result.output["error"]
        assert result.output["hint"] == "resolve_entity"


class TestUpdateClarifications:
    @pytest.mark.asyncio
    async def test_record_gap(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_clarifications",
            {
                "operation": "record_gap",
                "gap_type": "ENTITY_MISSING",
                "description": "How many guests attending?",
            },
        )
        assert result.ok
        assert result.output["success"]

    @pytest.mark.asyncio
    async def test_resolve_gap(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_clarifications",
            {
                "operation": "resolve_gap",
                "gap_id": "gap-001",
                "resolution": "6 guests attending",
            },
        )
        assert result.ok


class TestUpdateNarrative:
    @pytest.mark.asyncio
    async def test_new_thread(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "update_narrative",
            {
                "operation": "new_thread",
                "topic": "Birthday Dinner Planning",
                "goal": "Find vegan restaurant for Mom",
                "domains": ["dining", "family"],
            },
        )
        assert result.ok
        assert result.output["success"]
        assert result.output["thread_id"]
        assert result.output["thread_status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_close_thread(self, registry: ConciergeToolRegistry):
        # Create thread first
        create_result = await registry.execute(
            "update_narrative",
            {"operation": "new_thread", "topic": "Test thread", "goal": "Test"},
        )
        thread_id = create_result.output["thread_id"]

        # Close it
        result = await registry.execute(
            "update_narrative",
            {"operation": "close_thread", "thread_id": thread_id},
        )
        assert result.ok
        assert result.output["thread_status"] == "RESOLVED"


class TestRefineAffect:
    @pytest.mark.asyncio
    async def test_affect_override(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "refine_affect",
            {
                "override_emotion": "anticipation",
                "override_intensity": 0.8,
                "override_valence": "positive",
                "reasoning": "User is excited about the birthday",
            },
        )
        assert result.ok
        assert result.output["success"]
        assert result.output["override_applied"]


class TestPromoteBelief:
    @pytest.mark.asyncio
    async def test_promote_to_k0(self, registry: ConciergeToolRegistry):
        # First resolve entity and add a belief
        r = await registry.execute("resolve_entity", {"name": "Mom", "entity_type": "person"})
        entity_id = r.output["entity_id"]

        add_result = await registry.execute(
            "update_beliefs",
            {
                "operation": "add_fact",
                "entity_id": entity_id,
                "predicate": "diet",
                "object_value": "vegan",
            },
        )
        belief_id = add_result.output["belief_id"]

        # Promote it
        result = await registry.execute(
            "promote_belief",
            {
                "belief_id": belief_id,
                "direction": "hot_to_k0",
                "reason": "Important family dietary info",
            },
        )
        assert result.ok
        assert result.output["success"]
        assert result.output["destination"] == "k0"
        assert result.output["k0_store_receipt"]

    @pytest.mark.asyncio
    async def test_promote_warm_to_hot(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "promote_belief",
            {
                "belief_id": "warm-belief-001",
                "direction": "warm_to_hot",
                "reason": "Frequently referenced",
            },
        )
        assert result.ok
        assert result.output["destination"] == "beliefs_active"


# -----------------------------------------------------------------------
# Read tools
# -----------------------------------------------------------------------


class TestRecallMemory:
    @pytest.mark.asyncio
    async def test_recall_birthday(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "recall_memory",
            {"query": "birthday", "selectors": ["event", "preference"]},
        )
        assert result.ok
        assert "results" in result.output
        assert len(result.output["results"]) > 0

    @pytest.mark.asyncio
    async def test_recall_with_limit(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "recall_memory",
            {"query": "dinner restaurants", "max_results": 2},
        )
        assert result.ok
        assert len(result.output["results"]) <= 2


class TestDiscoverCapabilities:
    @pytest.mark.asyncio
    async def test_discover_dining(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "discover_capabilities",
            {"intent": "find restaurants", "domain": ["DINING"]},
        )
        assert result.ok
        assert "capabilities" in result.output
        assert len(result.output["capabilities"]) > 0


class TestSummarizeContext:
    @pytest.mark.asyncio
    async def test_summarize_empty_session(self, registry: ConciergeToolRegistry):
        result = await registry.execute("summarize_context", {})
        assert result.ok
        assert "summary" in result.output
        assert "original_tokens" in result.output

    @pytest.mark.asyncio
    async def test_summarize_after_mutations(self, registry: ConciergeToolRegistry):
        # Add some state first (with entity resolution)
        r = await registry.execute("resolve_entity", {"name": "Mom", "entity_type": "person"})
        entity_id = r.output["entity_id"]

        await registry.execute(
            "update_beliefs",
            {
                "operation": "add_fact",
                "entity_id": entity_id,
                "predicate": "diet",
                "object_value": "vegan",
            },
        )
        await registry.execute(
            "update_narrative",
            {"operation": "new_thread", "topic": "Birthday dinner"},
        )

        result = await registry.execute(
            "summarize_context",
            {"strategy": "extractive", "sections": ["beliefs_active", "narrative_active"]},
        )
        assert result.ok
        summary = result.output["summary"]
        assert "Mom" in summary or "vegan" in summary or "Birthday" in summary


# -----------------------------------------------------------------------
# Action tools
# -----------------------------------------------------------------------


class TestInvokeCapability:
    @pytest.mark.asyncio
    async def test_invoke_restaurant_search(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "invoke_capability",
            {
                "capability": "tool.execute.restaurant_search",
                "params": {"cuisine": "vegan", "location": "downtown", "party_size": 6},
            },
        )
        assert result.ok
        assert "results" in result.output or "restaurants" in str(result.output).lower()

    @pytest.mark.asyncio
    async def test_invoke_unknown_capability(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "invoke_capability",
            {
                "capability": "tool.execute.unknown_tool",
                "params": {},
            },
        )
        assert result.ok  # Returns canned response regardless


class TestSpawnViaFabric:
    @pytest.mark.asyncio
    async def test_spawn_agent(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "spawn_via_fabric",
            {
                "agent_name": "agent.execute.menu_planner",
                "description": "Plans dinner menus for dietary restrictions",
                "domain": ["dining", "nutrition"],
                "tools_granted": ["restaurant_search", "menu_lookup"],
                "llm_budget_tokens": 4096,
            },
        )
        assert result.ok
        assert result.output.get("agent_id")
        assert result.output.get("status") in ("registered", "spawned", "ready")


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_execute_workflow(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "execute_workflow",
            {
                "workflow_id": "workflow.birthday_party_planning",
                "params": {
                    "guest_count": 6,
                    "dietary_restrictions": ["vegan"],
                    "budget": 500,
                },
            },
        )
        assert result.ok
        assert "execution_id" in result.output or "status" in result.output


# -----------------------------------------------------------------------
# Final answer (meta)
# -----------------------------------------------------------------------


class TestFinalAnswer:
    @pytest.mark.asyncio
    async def test_final_answer(self, registry: ConciergeToolRegistry):
        result = await registry.execute(
            "final_answer",
            {"answer": "Here is the complete dinner plan for Mom's birthday..."},
        )
        assert result.ok
        assert result.output["complete"] is True
        assert "dinner plan" in result.output["answer"]


# -----------------------------------------------------------------------
# Integration: multi-tool sequence
# -----------------------------------------------------------------------


class TestMultiToolSequence:
    """Test a realistic sequence of tool calls mimicking Scenario 10."""

    @pytest.mark.asyncio
    async def test_birthday_dinner_flow(self, registry: ConciergeToolRegistry):
        # Step 1: Acknowledge
        r = await registry.execute(
            "acknowledge",
            {
                "ack_type": "commit",
                "message": "Planning birthday dinner for Mom.",
                "next_tool": "update_scoreboard",
            },
        )
        assert r.ok

        # Step 2: Set task in scoreboard
        r = await registry.execute(
            "update_scoreboard",
            {
                "operation": "set_task",
                "task_name": "plan_dinner",
                "task_status": "in_progress",
            },
        )
        assert r.ok
        assert r.output["success"]

        # Step 3a: Resolve entity for Mom
        r = await registry.execute("resolve_entity", {"name": "Mom", "entity_type": "person"})
        assert r.ok
        entity_id = r.output["entity_id"]

        # Step 3b: Record belief about Mom (with entity_id)
        r = await registry.execute(
            "update_beliefs",
            {
                "operation": "add_fact",
                "entity_id": entity_id,
                "predicate": "diet",
                "object_value": "vegan",
                "confidence": 0.95,
                "source": "user_stated",
            },
        )
        assert r.ok
        belief_id = r.output["belief_id"]

        # Step 4: Create narrative thread
        r = await registry.execute(
            "update_narrative",
            {
                "operation": "new_thread",
                "topic": "Birthday Dinner Planning",
                "goal": "Find and book vegan restaurant",
            },
        )
        assert r.ok
        thread_id = r.output["thread_id"]

        # Step 5: Recall memories
        r = await registry.execute(
            "recall_memory",
            {"query": "Mom birthday preferences restaurants"},
        )
        assert r.ok
        assert len(r.output["results"]) > 0

        # Step 6: Discover capabilities
        r = await registry.execute(
            "discover_capabilities",
            {"intent": "find vegan restaurants", "domain": ["dining"]},
        )
        assert r.ok

        # Step 7: Invoke restaurant search
        r = await registry.execute(
            "invoke_capability",
            {
                "capability": "tool.execute.restaurant_search",
                "params": {"cuisine": "vegan", "party_size": 6},
            },
        )
        assert r.ok

        # Step 8: Promote belief to K0
        r = await registry.execute(
            "promote_belief",
            {
                "belief_id": belief_id,
                "direction": "hot_to_k0",
                "reason": "Important family info",
            },
        )
        assert r.ok
        assert r.output["k0_store_receipt"]

        # Step 9: Summarize context
        r = await registry.execute("summarize_context", {})
        assert r.ok
        assert r.output["summary"]

        # Step 10: Close thread
        r = await registry.execute(
            "update_narrative",
            {"operation": "close_thread", "thread_id": thread_id},
        )
        assert r.ok

        # Step 11: Final answer
        r = await registry.execute(
            "final_answer",
            {"answer": "Booked Green Garden for 6 guests."},
        )
        assert r.ok
        assert r.output["complete"]
