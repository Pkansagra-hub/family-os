"""
k1.tools.mcp_servers.recipes.server -- Recipes MCP Server (FastMCP, SSE).

Built with FastMCP. Remote SSE transport for recipe discovery
and meal planning.

Usage:
  python -m k1.tools.mcp_servers.recipes.server

Testing:
  from fastmcp import Client
  async with Client(mcp) as client:
      result = await client.call_tool("recipe_search", {"query": "chicken"})

References:
  - fabric_tool_implementation_plan.md Phase 3, Section 5.2
"""

from __future__ import annotations

import logging
from typing import Optional

from fastmcp import FastMCP

from k1.tools.mcp_servers.recipes.api_client import RecipeAPIClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server + API Client
# ---------------------------------------------------------------------------

_api_client: Optional[RecipeAPIClient] = None


def _get_client() -> RecipeAPIClient:
    """Return the active RecipeAPIClient instance."""
    global _api_client
    if _api_client is None:
        _api_client = RecipeAPIClient()
    return _api_client


def set_api_client(client: RecipeAPIClient) -> None:
    """Inject an API client instance (for testing)."""
    global _api_client
    _api_client = client


mcp = FastMCP(
    "recipes-mcp-sse",
    instructions="Recipe discovery and meal planning for families.",
)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def recipe_search(
    query: str,
    cuisine: str | None = None,
    max_results: int = 10,
) -> dict:
    """Search for recipes by name or ingredients.

    Args:
        query: Recipe name or ingredient to search for.
        cuisine: Optional cuisine filter (e.g. italian, mexican, asian).
        max_results: Maximum recipes to return (default 10, max 50).

    Returns:
        Dictionary with 'recipes' list and 'count'.
    """
    if not query:
        raise ValueError("query is required")

    client = _get_client()
    recipes = await client.search_recipes(
        query=query,
        cuisine=cuisine,
        max_results=max_results,
    )
    return {
        "recipes": [r.to_search_result() for r in recipes],
        "count": len(recipes),
    }


@mcp.tool()
async def recipe_meal_plan(
    days: int,
    servings: int,
    cuisine: str | None = None,
    dietary: str | None = None,
) -> dict:
    """Generate a meal plan for the specified number of days.

    Args:
        days: Number of days to plan (1-7).
        servings: Number of servings per meal.
        cuisine: Optional preferred cuisine type.
        dietary: Optional dietary restriction (vegetarian, vegan, gluten-free, dairy-free).

    Returns:
        Dictionary with 'plan' (day-by-day meals), 'days', and 'servings'.
    """
    if days < 1:
        raise ValueError("days must be at least 1")
    if servings < 1:
        raise ValueError("servings must be at least 1")

    client = _get_client()
    plan = await client.generate_meal_plan(
        days=days,
        servings=servings,
        cuisine=cuisine,
        dietary=dietary,
    )
    return plan.to_dict()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def create_server(api_client: Optional[RecipeAPIClient] = None) -> FastMCP:
    """
    Create and configure the recipes MCP server.

    Args:
        api_client: Optional RecipeAPIClient. Defaults to built-in.

    Returns:
        Configured FastMCP instance.
    """
    if api_client:
        set_api_client(api_client)
    return mcp


if __name__ == "__main__":
    create_server()
    mcp.run()
