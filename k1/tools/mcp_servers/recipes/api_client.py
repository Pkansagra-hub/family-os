"""
k1.tools.mcp_servers.recipes.api_client -- Recipe data provider.

Deterministic recipe data source for testing. Same pattern as
WeatherAPIClient: hash-based determinism, no network dependency.
Subclass and override for real API integration (Spoonacular, etc.).

References:
  - fabric_tool_implementation_plan.md Phase 3, Section 5.2
"""

from __future__ import annotations

from typing import List, Optional

from k1.tools.mcp_servers.recipes.models import DayPlan, Meal, MealPlan, Recipe

# ---------------------------------------------------------------------------
# Built-in recipe database (deterministic test data)
# ---------------------------------------------------------------------------

_RECIPES: List[Recipe] = [
    Recipe(
        recipe_id="r-001",
        title="Spaghetti Bolognese",
        cuisine="italian",
        prep_time_min=45,
        ingredients=("spaghetti", "ground beef", "tomato sauce", "onion", "garlic"),
    ),
    Recipe(
        recipe_id="r-002",
        title="Chicken Tacos",
        cuisine="mexican",
        prep_time_min=25,
        ingredients=("chicken", "tortilla", "salsa", "cheese", "lettuce"),
    ),
    Recipe(
        recipe_id="r-003",
        title="Pad Thai",
        cuisine="asian",
        prep_time_min=30,
        ingredients=("rice noodles", "shrimp", "peanuts", "bean sprouts", "lime"),
    ),
    Recipe(
        recipe_id="r-004",
        title="Caesar Salad",
        cuisine="american",
        prep_time_min=15,
        ingredients=("romaine", "croutons", "parmesan", "caesar dressing"),
    ),
    Recipe(
        recipe_id="r-005",
        title="Vegetable Stir Fry",
        cuisine="asian",
        prep_time_min=20,
        ingredients=("broccoli", "carrot", "bell pepper", "soy sauce", "tofu"),
    ),
    Recipe(
        recipe_id="r-006",
        title="Margherita Pizza",
        cuisine="italian",
        prep_time_min=35,
        ingredients=("pizza dough", "mozzarella", "tomato", "basil"),
    ),
    Recipe(
        recipe_id="r-007",
        title="Fish and Chips",
        cuisine="british",
        prep_time_min=40,
        ingredients=("cod", "potatoes", "flour", "beer", "peas"),
    ),
    Recipe(
        recipe_id="r-008",
        title="Chicken Curry",
        cuisine="indian",
        prep_time_min=50,
        ingredients=("chicken", "curry paste", "coconut milk", "rice", "onion"),
    ),
    Recipe(
        recipe_id="r-009",
        title="Greek Salad",
        cuisine="greek",
        prep_time_min=10,
        ingredients=("cucumber", "tomato", "feta", "olive", "red onion"),
    ),
    Recipe(
        recipe_id="r-010",
        title="Beef Burrito Bowl",
        cuisine="mexican",
        prep_time_min=30,
        ingredients=("beef", "rice", "black beans", "corn", "avocado"),
    ),
    Recipe(
        recipe_id="r-011",
        title="Pancakes",
        cuisine="american",
        prep_time_min=20,
        ingredients=("flour", "eggs", "milk", "butter", "maple syrup"),
    ),
    Recipe(
        recipe_id="r-012",
        title="Mushroom Risotto",
        cuisine="italian",
        prep_time_min=40,
        ingredients=("arborio rice", "mushrooms", "parmesan", "onion", "white wine"),
    ),
]

_MEAL_TYPES = ("breakfast", "lunch", "dinner")


class RecipeAPIClient:
    """
    Recipe data provider.

    Default implementation uses a built-in recipe database.
    Deterministic and stable for testing.
    """

    async def search_recipes(
        self,
        query: str,
        cuisine: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Recipe]:
        """
        Search recipes by name or ingredient.

        Case-insensitive substring match across title and ingredients.
        """
        max_results = max(1, min(max_results, 50))
        q = query.lower()
        matches: List[Recipe] = []

        for recipe in _RECIPES:
            if q in recipe.title.lower():
                matches.append(recipe)
            elif any(q in ing.lower() for ing in recipe.ingredients):
                matches.append(recipe)

        if cuisine:
            c = cuisine.lower()
            matches = [r for r in matches if r.cuisine.lower() == c]

        return matches[:max_results]

    async def generate_meal_plan(
        self,
        days: int,
        servings: int,
        cuisine: Optional[str] = None,
        dietary: Optional[str] = None,
    ) -> MealPlan:
        """
        Generate a deterministic meal plan.

        Selects recipes round-robin from the database, filtered by
        optional cuisine/dietary preferences.
        """
        days = max(1, min(days, 7))
        pool = list(_RECIPES)

        if cuisine:
            c = cuisine.lower()
            filtered = [r for r in pool if r.cuisine.lower() == c]
            if filtered:
                pool = filtered

        if dietary and dietary != "none":
            d = dietary.lower()
            if d == "vegetarian" or d == "vegan":
                meat = {"chicken", "beef", "shrimp", "cod", "ground beef"}
                pool = [
                    r
                    for r in pool
                    if not any(m in ing.lower() for ing in r.ingredients for m in meat)
                ]

        if not pool:
            pool = list(_RECIPES)  # fallback

        day_plans = []
        idx = 0
        for day_num in range(1, days + 1):
            meals = []
            for meal_type in _MEAL_TYPES:
                recipe = pool[idx % len(pool)]
                meals.append(
                    Meal(
                        meal_type=meal_type,
                        recipe_id=recipe.recipe_id,
                        title=recipe.title,
                        prep_time_min=recipe.prep_time_min,
                    )
                )
                idx += 1
            day_plans.append(DayPlan(day=day_num, meals=tuple(meals)))

        return MealPlan(
            plan=tuple(day_plans),
            days=days,
            servings=servings,
        )
