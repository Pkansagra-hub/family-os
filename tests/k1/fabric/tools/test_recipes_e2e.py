"""
Integration tests for Phase 3 -- Recipes MCP Server (FastMCP, SSE).

Tests the full recipes tool stack:
  - Recipe / Meal / DayPlan / MealPlan models (frozen, to_dict)
  - RecipeAPIClient (built-in recipe database, deterministic)
  - FastMCP server (tool registration, call_tool via Client)
  - Contract YAML parsing and validation

NO MOCKS -- all tests use real components.

References:
  - fabric_tool_implementation_plan.md Phase 3, Section 5.2
  - tests/k1/fabric/tools/test_weather_e2e.py (pattern)
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastmcp import Client

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import CapabilityContract
from k1.tools.mcp_servers.recipes.api_client import _RECIPES, RecipeAPIClient
from k1.tools.mcp_servers.recipes.models import DayPlan, Meal, MealPlan, Recipe
from k1.tools.mcp_servers.recipes.server import create_server, mcp

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts" / "tools"


# =========================================================================
# Section 1: Recipe models
# =========================================================================


class TestRecipeModels:
    """Recipe / Meal / DayPlan / MealPlan frozen dataclass behavior."""

    def test_recipe_default(self) -> None:
        r = Recipe()
        assert r.title == ""
        assert r.recipe_id != ""  # UUID auto-generated

    def test_recipe_full(self) -> None:
        r = Recipe(
            recipe_id="r-x",
            title="Pasta",
            cuisine="italian",
            prep_time_min=30,
            ingredients=("pasta", "sauce"),
        )
        assert r.recipe_id == "r-x"
        assert r.ingredients == ("pasta", "sauce")

    def test_recipe_frozen(self) -> None:
        r = Recipe(title="Test")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            r.title = "Changed"  # type: ignore[misc]

    def test_recipe_to_dict(self) -> None:
        r = Recipe(recipe_id="r-1", title="Tacos", cuisine="mexican", prep_time_min=25)
        d = r.to_dict()
        assert d["recipe_id"] == "r-1"
        assert d["cuisine"] == "mexican"
        assert d["ingredients"] == []

    def test_recipe_to_search_result(self) -> None:
        r = Recipe(recipe_id="r-2", title="Salad", ingredients=("lettuce",), instructions="Mix")
        s = r.to_search_result()
        assert "instructions" not in s
        assert s["ingredients"] == ["lettuce"]

    def test_recipe_from_dict(self) -> None:
        r = Recipe.from_dict(
            {"recipe_id": "r-3", "title": "Curry", "ingredients": ["chicken", "spice"]}
        )
        assert r.recipe_id == "r-3"
        assert r.ingredients == ("chicken", "spice")

    def test_meal_to_dict(self) -> None:
        m = Meal(meal_type="dinner", recipe_id="r-1", title="Pasta", prep_time_min=30)
        d = m.to_dict()
        assert d["meal_type"] == "dinner"

    def test_day_plan_to_dict(self) -> None:
        dp = DayPlan(day=1, meals=(Meal(meal_type="breakfast", recipe_id="r-1", title="Eggs"),))
        d = dp.to_dict()
        assert d["day"] == 1
        assert len(d["meals"]) == 1

    def test_meal_plan_to_dict(self) -> None:
        mp = MealPlan(
            plan=(DayPlan(day=1, meals=()),),
            days=1,
            servings=4,
        )
        d = mp.to_dict()
        assert d["days"] == 1
        assert d["servings"] == 4


# =========================================================================
# Section 2: RecipeAPIClient
# =========================================================================


class TestRecipeAPIClient:
    """RecipeAPIClient deterministic data."""

    @pytest.fixture()
    def client(self) -> RecipeAPIClient:
        return RecipeAPIClient()

    @pytest.mark.asyncio
    async def test_search_by_title(self, client: RecipeAPIClient) -> None:
        results = await client.search_recipes("spaghetti")
        assert len(results) >= 1
        assert any("spaghetti" in r.title.lower() for r in results)

    @pytest.mark.asyncio
    async def test_search_by_ingredient(self, client: RecipeAPIClient) -> None:
        results = await client.search_recipes("chicken")
        assert len(results) >= 1
        # at least one recipe has chicken in ingredients
        assert any("chicken" in ing for r in results for ing in r.ingredients)

    @pytest.mark.asyncio
    async def test_search_with_cuisine_filter(self, client: RecipeAPIClient) -> None:
        results = await client.search_recipes("chicken", cuisine="mexican")
        for r in results:
            assert r.cuisine == "mexican"

    @pytest.mark.asyncio
    async def test_search_no_results(self, client: RecipeAPIClient) -> None:
        results = await client.search_recipes("xyznonexistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client: RecipeAPIClient) -> None:
        # broad query that matches multiple recipes
        results = await client.search_recipes("chicken", max_results=1)
        assert len(results) <= 1

    @pytest.mark.asyncio
    async def test_generate_meal_plan(self, client: RecipeAPIClient) -> None:
        plan = await client.generate_meal_plan(days=3, servings=4)
        assert isinstance(plan, MealPlan)
        assert plan.days == 3
        assert plan.servings == 4
        assert len(plan.plan) == 3
        for day in plan.plan:
            assert len(day.meals) == 3  # breakfast, lunch, dinner

    @pytest.mark.asyncio
    async def test_meal_plan_clamps_days(self, client: RecipeAPIClient) -> None:
        plan = await client.generate_meal_plan(days=20, servings=2)
        assert plan.days == 7  # max 7

    @pytest.mark.asyncio
    async def test_meal_plan_min_1_day(self, client: RecipeAPIClient) -> None:
        plan = await client.generate_meal_plan(days=0, servings=2)
        assert plan.days == 1

    @pytest.mark.asyncio
    async def test_meal_plan_with_cuisine(self, client: RecipeAPIClient) -> None:
        plan = await client.generate_meal_plan(days=1, servings=2, cuisine="italian")
        # all meals should be italian if enough recipes exist
        for day in plan.plan:
            for meal in day.meals:
                assert meal.title != ""

    @pytest.mark.asyncio
    async def test_meal_plan_vegetarian(self, client: RecipeAPIClient) -> None:
        plan = await client.generate_meal_plan(days=1, servings=2, dietary="vegetarian")
        assert len(plan.plan) == 1
        # should have meals (fallback if no vegetarian recipes)
        assert len(plan.plan[0].meals) == 3

    @pytest.mark.asyncio
    async def test_deterministic(self, client: RecipeAPIClient) -> None:
        p1 = await client.generate_meal_plan(days=2, servings=4)
        p2 = await client.generate_meal_plan(days=2, servings=4)
        assert p1.to_dict() == p2.to_dict()

    def test_built_in_database_has_recipes(self) -> None:
        assert len(_RECIPES) >= 10


# =========================================================================
# Section 3: FastMCP Server (via Client)
# =========================================================================


class TestRecipesMCPServer:
    """Recipes MCP server via FastMCP Client."""

    @pytest.fixture(autouse=True)
    def _setup_server(self) -> None:
        create_server()

    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert names == {"recipe_search", "recipe_meal_plan"}

    @pytest.mark.asyncio
    async def test_search_chicken(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool("recipe_search", {"query": "chicken"})
            assert result.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_search_with_cuisine(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recipe_search", {"query": "chicken", "cuisine": "mexican"}
            )
            for r in result.data["recipes"]:
                assert r["cuisine"] == "mexican"

    @pytest.mark.asyncio
    async def test_search_no_results(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool("recipe_search", {"query": "zzz_nothing"})
            assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_query_error(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recipe_search",
                {"query": ""},
                raise_on_error=False,
            )
            assert result.is_error is True

    @pytest.mark.asyncio
    async def test_meal_plan(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool("recipe_meal_plan", {"days": 3, "servings": 4})
            assert result.data["days"] == 3
            assert result.data["servings"] == 4
            assert len(result.data["plan"]) == 3

    @pytest.mark.asyncio
    async def test_meal_plan_day_structure(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool("recipe_meal_plan", {"days": 1, "servings": 2})
            day = result.data["plan"][0]
            assert day["day"] == 1
            assert len(day["meals"]) == 3
            meal_types = {m["meal_type"] for m in day["meals"]}
            assert meal_types == {"breakfast", "lunch", "dinner"}

    @pytest.mark.asyncio
    async def test_meal_plan_with_cuisine(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recipe_meal_plan",
                {"days": 1, "servings": 2, "cuisine": "italian"},
            )
            assert result.data["days"] == 1

    @pytest.mark.asyncio
    async def test_meal_plan_with_dietary(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recipe_meal_plan",
                {"days": 1, "servings": 2, "dietary": "vegetarian"},
            )
            assert result.data["days"] == 1
            assert len(result.data["plan"][0]["meals"]) == 3

    @pytest.mark.asyncio
    async def test_meal_plan_zero_days_error(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recipe_meal_plan",
                {"days": 0, "servings": 2},
                raise_on_error=False,
            )
            assert result.is_error is True

    @pytest.mark.asyncio
    async def test_meal_plan_zero_servings_error(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recipe_meal_plan",
                {"days": 1, "servings": 0},
                raise_on_error=False,
            )
            assert result.is_error is True


# =========================================================================
# Section 4: Contract YAML parsing
# =========================================================================


class TestRecipesContracts:
    """Parse and validate recipes contract YAML files."""

    @pytest.fixture()
    def validator(self) -> ContractValidator:
        return ContractValidator()

    def test_search_contract_parses(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_search.yaml", validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.read.recipe_search"
        assert contract.version == "1.0.0"

    def test_search_contract_green_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_search.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_search_contract_provider(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_search.yaml", validator=validator)
        assert contract.provider_type == "MCP"
        assert contract.provider_id == "recipes_mcp_sse"

    def test_search_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_search.yaml", validator=validator)
        required = [inp.name for inp in contract.required_inputs]
        assert "query" in required

    def test_meal_plan_contract_parses(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_meal_plan.yaml", validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.write.recipe_meal_plan"

    def test_meal_plan_contract_amber_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_meal_plan.yaml", validator=validator)
        assert contract.safety_band_min == "AMBER"

    def test_meal_plan_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_meal_plan.yaml", validator=validator)
        required = [inp.name for inp in contract.required_inputs]
        assert "days" in required
        assert "servings" in required

    def test_both_share_provider_id(self, validator: ContractValidator) -> None:
        ids = set()
        for name in ["recipe_search.yaml", "recipe_meal_plan.yaml"]:
            c = parse_contract(CONTRACTS_DIR / name, validator=validator)
            ids.add(c.provider_id)
        assert ids == {"recipes_mcp_sse"}

    def test_both_share_domain(self, validator: ContractValidator) -> None:
        for name in ["recipe_search.yaml", "recipe_meal_plan.yaml"]:
            c = parse_contract(CONTRACTS_DIR / name, validator=validator)
            assert "RECIPES" in c.domain

    def test_search_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_search.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "recipes" in props
        assert "count" in props

    def test_meal_plan_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "recipe_meal_plan.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "plan" in props
        assert "days" in props
        assert "servings" in props
