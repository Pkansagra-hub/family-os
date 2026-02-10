"""
Integration tests for Phase 3 -- Batch Composition & Multi-Tool Execution.

Two testing levels:

  Level 1: Fabric execute_batch() -- tests batch orchestration strategies
    (PARALLEL, SEQUENTIAL, DAG) through the full Fabric pipeline.
    Uses FabricFactory.create_for_testing() with real contracts.

  Level 2: FastMCP Client composition -- tests real multi-server tool
    composition across notes (stdio) and recipes (SSE) servers.
    Uses asyncio.gather for parallelism, sequential chaining,
    and DAG-style (search -> compose -> verify) patterns.

NO MOCKS. All tests use real components.

References:
  - fabric_tool_implementation_plan.md Phase 3, Section 5.3
  - ADR 0078: Tool Call Batching Pipeline
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastmcp import Client

from k1.fabric.fabric import BatchStrategy
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.tools.mcp_servers.notes.server import create_server as create_notes_server
from k1.tools.mcp_servers.notes.server import mcp as notes_mcp
from k1.tools.mcp_servers.recipes.server import create_server as create_recipes_server
from k1.tools.mcp_servers.recipes.server import mcp as recipes_mcp

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    name: str,
    params: dict | None = None,
    request_id: str = "",
    caller: str = "test",
) -> CapabilityRequest:
    """Build a CapabilityRequest with sensible defaults."""
    return CapabilityRequest(
        capability_name=name,
        params=params or {},
        caller=caller,
        **({"request_id": request_id} if request_id else {}),
    )


# =========================================================================
# Level 1: Fabric execute_batch() orchestration
# =========================================================================


class TestFabricBatchParallel:
    """BatchStrategy.PARALLEL -- asyncio.gather all requests."""

    @pytest.fixture()
    def fabric(self):
        return FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(CONTRACTS_DIR),
        )

    @pytest.mark.asyncio
    async def test_parallel_returns_same_count(self, fabric) -> None:
        reqs = [
            _make_request("tool.read.calendar_list_events"),
            _make_request("tool.read.weather_current"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.PARALLEL)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_parallel_preserves_input_order(self, fabric) -> None:
        reqs = [
            _make_request("tool.read.calendar_list_events", request_id="req-A"),
            _make_request("tool.read.weather_current", request_id="req-B"),
            _make_request("tool.read.notes_list", request_id="req-C"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.PARALLEL)
        assert [r.request_id for r in results] == ["req-A", "req-B", "req-C"]

    @pytest.mark.asyncio
    async def test_parallel_error_isolation(self, fabric) -> None:
        """One failing request should not block others."""
        reqs = [
            _make_request("tool.read.calendar_list_events"),
            _make_request("tool.nonexistent.fake_tool"),
            _make_request("tool.read.weather_current"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.PARALLEL)
        assert len(results) == 3
        # All should have results (success or failure), not exceptions
        for r in results:
            assert isinstance(r, CapabilityResult)

    @pytest.mark.asyncio
    async def test_parallel_multiple_providers(self, fabric) -> None:
        """Cross-provider: MCP + WASM tools in one batch."""
        reqs = [
            _make_request("tool.read.notes_list"),  # MCP stdio
            _make_request("tool.read.recipe_search"),  # MCP SSE
            _make_request("tool.execute.date_calc"),  # WASM
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.PARALLEL)
        assert len(results) == 3


class TestFabricBatchSequential:
    """BatchStrategy.SEQUENTIAL -- requests execute one-by-one."""

    @pytest.fixture()
    def fabric(self):
        return FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(CONTRACTS_DIR),
        )

    @pytest.mark.asyncio
    async def test_sequential_returns_same_count(self, fabric) -> None:
        reqs = [
            _make_request("tool.write.notes_create"),
            _make_request("tool.read.notes_search"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.SEQUENTIAL)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_sequential_preserves_order(self, fabric) -> None:
        reqs = [
            _make_request("tool.write.notes_create", request_id="create-1"),
            _make_request("tool.read.notes_search", request_id="search-1"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.SEQUENTIAL)
        assert results[0].request_id == "create-1"
        assert results[1].request_id == "search-1"

    @pytest.mark.asyncio
    async def test_sequential_failure_doesnt_block_next(self, fabric) -> None:
        reqs = [
            _make_request("tool.nonexistent.bad_tool"),
            _make_request("tool.read.notes_list"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.SEQUENTIAL)
        assert len(results) == 2
        # Second request still executes despite first failing
        assert isinstance(results[1], CapabilityResult)


class TestFabricBatchDAG:
    """BatchStrategy.DAG -- dependency-aware topological execution."""

    @pytest.fixture()
    def fabric(self):
        return FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(CONTRACTS_DIR),
        )

    @pytest.mark.asyncio
    async def test_dag_independent_requests(self, fabric) -> None:
        """No dependencies = all execute in first wave."""
        reqs = [
            _make_request("tool.read.recipe_search", request_id="r1"),
            _make_request("tool.read.notes_list", request_id="r2"),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.DAG)
        assert len(results) == 2
        assert results[0].request_id == "r1"
        assert results[1].request_id == "r2"

    @pytest.mark.asyncio
    async def test_dag_with_dependency(self, fabric) -> None:
        """Second request depends on first via _depends_on."""
        reqs = [
            _make_request(
                "tool.read.recipe_search",
                request_id="search-step",
                params={"query": "chicken"},
            ),
            _make_request(
                "tool.write.calendar_create_event",
                request_id="create-step",
                params={"_depends_on": ["search-step"], "title": "Cook chicken"},
            ),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.DAG)
        assert len(results) == 2
        # Both should have results, second waited for first
        assert results[0].request_id == "search-step"
        assert results[1].request_id == "create-step"

    @pytest.mark.asyncio
    async def test_dag_chain(self, fabric) -> None:
        """3-step chain: A -> B -> C."""
        reqs = [
            _make_request("tool.read.recipe_search", request_id="step-a"),
            _make_request(
                "tool.write.notes_create",
                request_id="step-b",
                params={"_depends_on": ["step-a"]},
            ),
            _make_request(
                "tool.read.notes_search",
                request_id="step-c",
                params={"_depends_on": ["step-b"]},
            ),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.DAG)
        assert len(results) == 3
        # Order matches input order
        assert [r.request_id for r in results] == ["step-a", "step-b", "step-c"]

    @pytest.mark.asyncio
    async def test_dag_diamond(self, fabric) -> None:
        """Diamond: A -> (B, C) -> D."""
        reqs = [
            _make_request("tool.read.recipe_search", request_id="A"),
            _make_request(
                "tool.read.notes_list",
                request_id="B",
                params={"_depends_on": ["A"]},
            ),
            _make_request(
                "tool.read.weather_current",
                request_id="C",
                params={"_depends_on": ["A"]},
            ),
            _make_request(
                "tool.write.notes_create",
                request_id="D",
                params={"_depends_on": ["B", "C"]},
            ),
        ]
        results = await fabric.execute_batch(reqs, BatchStrategy.DAG)
        assert len(results) == 4
        assert [r.request_id for r in results] == ["A", "B", "C", "D"]


class TestFabricBatchGuardrails:
    """Batch edge cases: empty, size limits, unknown strategy handling."""

    @pytest.fixture()
    def fabric(self):
        return FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(CONTRACTS_DIR),
        )

    @pytest.mark.asyncio
    async def test_empty_batch(self, fabric) -> None:
        results = await fabric.execute_batch([], BatchStrategy.PARALLEL)
        assert results == []

    @pytest.mark.asyncio
    async def test_single_item_batch(self, fabric) -> None:
        reqs = [_make_request("tool.read.notes_list")]
        results = await fabric.execute_batch(reqs, BatchStrategy.PARALLEL)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_batch_size_exceeded(self, fabric) -> None:
        from k1.fabric.fabric import BatchSizeExceededError, FabricConfig

        small_fabric = FabricFactory.create_for_testing(
            contracts_dir=str(CONTRACTS_DIR),
            config=FabricConfig(max_batch_size=2),
        )
        reqs = [_make_request("tool.read.notes_list") for _ in range(5)]
        with pytest.raises(BatchSizeExceededError) as exc_info:
            await small_fabric.execute_batch(reqs, BatchStrategy.PARALLEL)
        assert exc_info.value.actual == 5
        assert exc_info.value.maximum == 2

    @pytest.mark.asyncio
    async def test_all_strategies_accept_same_requests(self, fabric) -> None:
        reqs = [
            _make_request("tool.read.notes_list", request_id="req-1"),
            _make_request("tool.read.recipe_search", request_id="req-2"),
        ]
        for strategy in BatchStrategy:
            results = await fabric.execute_batch(reqs, strategy)
            assert len(results) == 2


class TestFabricLearningSignals:
    """Verify learning signals are emitted for batched requests."""

    @pytest.fixture()
    def fabric(self):
        return FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(CONTRACTS_DIR),
        )

    @pytest.mark.asyncio
    async def test_learning_signals_emitted_per_request(self, fabric) -> None:
        """Each request in batch emits invoked + failed/completed events."""
        reqs = [
            _make_request("tool.read.notes_list"),
            _make_request("tool.read.recipe_search"),
        ]
        await fabric.execute_batch(reqs, BatchStrategy.PARALLEL)

        # Each execute() emits at least an invoked event
        invoked = fabric.event_port.get_captured(topic="k1.capability.invoked.v1")
        assert len(invoked) >= len(reqs)

        # Each also emits failed (no provider) or completed
        failed = fabric.event_port.get_captured(topic="k1.capability.failed.v1")
        completed = fabric.event_port.get_captured(topic="k1.capability.completed.v1")
        assert len(failed) + len(completed) >= len(reqs)


# =========================================================================
# Level 2: FastMCP Client multi-server composition
# =========================================================================


class TestMCPCompositionParallel:
    """Parallel tool calls across notes + recipes servers."""

    @pytest.fixture(autouse=True)
    def _setup_servers(self) -> None:
        create_notes_server(":memory:")
        create_recipes_server()

    @pytest.mark.asyncio
    async def test_parallel_search_across_servers(self) -> None:
        """Search notes + recipes simultaneously via asyncio.gather."""

        async def search_notes():
            async with Client(notes_mcp) as client:
                return await client.call_tool("notes_list", {})

        async def search_recipes():
            async with Client(recipes_mcp) as client:
                return await client.call_tool("recipe_search", {"query": "chicken"})

        notes_result, recipes_result = await asyncio.gather(search_notes(), search_recipes())

        assert notes_result.data["count"] >= 0
        assert recipes_result.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_parallel_create_then_read_across_servers(self) -> None:
        """Create a note and search recipes in parallel."""

        async def create_note():
            async with Client(notes_mcp) as client:
                return await client.call_tool(
                    "notes_create",
                    {"title": "Dinner Plan", "content": "Cook chicken tacos"},
                )

        async def search_recipes():
            async with Client(recipes_mcp) as client:
                return await client.call_tool("recipe_search", {"query": "tacos"})

        note_result, recipe_result = await asyncio.gather(create_note(), search_recipes())

        assert note_result.data["status"] == "created"
        assert recipe_result.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_parallel_meal_plan_and_notes_list(self) -> None:
        """Meal plan generation + notes list in parallel."""

        async def get_meal_plan():
            async with Client(recipes_mcp) as client:
                return await client.call_tool("recipe_meal_plan", {"days": 3, "servings": 4})

        async def list_notes():
            async with Client(notes_mcp) as client:
                return await client.call_tool("notes_list", {})

        plan_result, notes_result = await asyncio.gather(get_meal_plan(), list_notes())

        assert plan_result.data["days"] == 3
        assert notes_result.data["count"] >= 0


class TestMCPCompositionSequential:
    """Sequential tool calls: output of one feeds the next."""

    @pytest.fixture(autouse=True)
    def _setup_servers(self) -> None:
        create_notes_server(":memory:")
        create_recipes_server()

    @pytest.mark.asyncio
    async def test_create_then_search_note(self) -> None:
        """Create a note, then search for it by content."""
        async with Client(notes_mcp) as client:
            # Step 1: Create
            create_result = await client.call_tool(
                "notes_create",
                {"title": "Grocery List", "content": "Buy milk and eggs"},
            )
            assert create_result.data["status"] == "created"

            # Step 2: Search using content from step 1
            search_result = await client.call_tool("notes_search", {"query": "milk"})
            assert search_result.data["count"] >= 1
            assert any(
                "milk" in r.get("snippet", "").lower() for r in search_result.data["results"]
            )

    @pytest.mark.asyncio
    async def test_create_then_list_with_tag_filter(self) -> None:
        """Create tagged note, then list filtered by tag."""
        async with Client(notes_mcp) as client:
            await client.call_tool(
                "notes_create",
                {"title": "Recipe Note", "content": "Pasta recipe", "tags": "food,pasta"},
            )
            result = await client.call_tool("notes_list", {"tag": "food"})
            assert result.data["count"] >= 1
            assert any("Recipe Note" in n["title"] for n in result.data["notes"])

    @pytest.mark.asyncio
    async def test_multiple_creates_then_search(self) -> None:
        """Create several notes, then search to verify all indexed."""
        async with Client(notes_mcp) as client:
            topics = ["breakfast", "lunch", "dinner"]
            for topic in topics:
                await client.call_tool(
                    "notes_create",
                    {"title": f"{topic} plan", "content": f"Plan for {topic} today"},
                )

            for topic in topics:
                result = await client.call_tool("notes_search", {"query": topic})
                assert result.data["count"] >= 1


class TestMCPCompositionDAG:
    """DAG-style: search -> compose -> verify (cross-server)."""

    @pytest.fixture(autouse=True)
    def _setup_servers(self) -> None:
        create_notes_server(":memory:")
        create_recipes_server()

    @pytest.mark.asyncio
    async def test_search_recipes_then_create_note(self) -> None:
        """Search recipes -> create note with recipe info -> verify."""
        # Step 1: Search recipes
        async with Client(recipes_mcp) as client:
            search_result = await client.call_tool("recipe_search", {"query": "spaghetti"})
        assert search_result.data["count"] >= 1
        recipe = search_result.data["recipes"][0]

        # Step 2: Create note from recipe data (feeds into notes server)
        async with Client(notes_mcp) as client:
            create_result = await client.call_tool(
                "notes_create",
                {
                    "title": f"Try: {recipe['title']}",
                    "content": f"Ingredients: {', '.join(recipe['ingredients'])}",
                    "tags": "recipe,todo",
                },
            )
        assert create_result.data["status"] == "created"

        # Step 3: Verify note appears in search
        async with Client(notes_mcp) as client:
            verify_result = await client.call_tool("notes_search", {"query": recipe["title"]})
        assert verify_result.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_meal_plan_to_notes(self) -> None:
        """Generate meal plan -> create note per day -> list all."""
        # Step 1: Generate meal plan
        async with Client(recipes_mcp) as client:
            plan_result = await client.call_tool("recipe_meal_plan", {"days": 2, "servings": 4})
        plan = plan_result.data

        # Step 2: Create a note for each day
        async with Client(notes_mcp) as client:
            for day in plan["plan"]:
                meals = ", ".join(m["title"] for m in day["meals"])
                await client.call_tool(
                    "notes_create",
                    {
                        "title": f"Day {day['day']} Meals",
                        "content": meals,
                        "tags": "meal-plan",
                    },
                )

        # Step 3: Verify all day notes exist
        async with Client(notes_mcp) as client:
            list_result = await client.call_tool("notes_list", {"tag": "meal-plan"})
        assert list_result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_filtered_search_then_compose(self) -> None:
        """Search with cuisine filter -> create shopping note."""
        # Step 1: Search Italian recipes
        async with Client(recipes_mcp) as client:
            search_result = await client.call_tool(
                "recipe_search", {"query": "spaghetti", "cuisine": "italian"}
            )
        recipes = search_result.data["recipes"]
        assert len(recipes) >= 1

        # Step 2: Aggregate ingredients into shopping note
        all_ingredients = set()
        for r in recipes:
            all_ingredients.update(r["ingredients"])

        async with Client(notes_mcp) as client:
            create_result = await client.call_tool(
                "notes_create",
                {
                    "title": "Italian Shopping List",
                    "content": ", ".join(sorted(all_ingredients)),
                    "tags": "shopping,italian",
                },
            )
        assert create_result.data["status"] == "created"

        # Step 3: Verify searchable
        async with Client(notes_mcp) as client:
            verify = await client.call_tool("notes_search", {"query": "Italian Shopping"})
        assert verify.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_parallel_searches_then_sequential_compose(self) -> None:
        """Parallel: search recipes + list notes -> Sequential: create summary note."""

        # Wave 1: Two parallel searches
        async def search_recipes():
            async with Client(recipes_mcp) as client:
                return await client.call_tool("recipe_search", {"query": "chicken"})

        async def list_notes():
            async with Client(notes_mcp) as client:
                return await client.call_tool("notes_list", {})

        recipe_result, notes_result = await asyncio.gather(search_recipes(), list_notes())

        # Wave 2: Create summary note from both results
        async with Client(notes_mcp) as client:
            summary = (
                f"Found {recipe_result.data['count']} chicken recipes, "
                f"{notes_result.data['count']} existing notes"
            )
            create_result = await client.call_tool(
                "notes_create",
                {"title": "Daily Summary", "content": summary},
            )
        assert create_result.data["status"] == "created"
