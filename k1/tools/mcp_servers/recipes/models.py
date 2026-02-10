"""
k1.tools.mcp_servers.recipes.models -- Recipe data models.

Frozen dataclasses for recipe data. Immutable after construction.

References:
  - recipe_search.yaml, recipe_meal_plan.yaml
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class Recipe:
    """A single recipe with ingredients and prep info."""

    recipe_id: str = ""
    title: str = ""
    cuisine: str = ""
    prep_time_min: int = 0
    ingredients: Tuple[str, ...] = ()
    instructions: str = ""

    def __post_init__(self) -> None:
        if not self.recipe_id:
            object.__setattr__(self, "recipe_id", str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "title": self.title,
            "cuisine": self.cuisine,
            "prep_time_min": self.prep_time_min,
            "ingredients": list(self.ingredients),
            "instructions": self.instructions,
        }

    def to_search_result(self) -> Dict[str, Any]:
        """Search result dict (no instructions)."""
        return {
            "recipe_id": self.recipe_id,
            "title": self.title,
            "cuisine": self.cuisine,
            "prep_time_min": self.prep_time_min,
            "ingredients": list(self.ingredients),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recipe":
        return cls(
            recipe_id=data.get("recipe_id", ""),
            title=data.get("title", ""),
            cuisine=data.get("cuisine", ""),
            prep_time_min=int(data.get("prep_time_min", 0)),
            ingredients=tuple(data.get("ingredients", [])),
            instructions=data.get("instructions", ""),
        )


@dataclass(frozen=True)
class Meal:
    """A single meal within a day plan."""

    meal_type: str = ""  # breakfast, lunch, dinner
    recipe_id: str = ""
    title: str = ""
    prep_time_min: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meal_type": self.meal_type,
            "recipe_id": self.recipe_id,
            "title": self.title,
            "prep_time_min": self.prep_time_min,
        }


@dataclass(frozen=True)
class DayPlan:
    """A single day's meals."""

    day: int = 1
    meals: Tuple[Meal, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "meals": [m.to_dict() for m in self.meals],
        }


@dataclass(frozen=True)
class MealPlan:
    """Complete meal plan over multiple days."""

    plan: Tuple[DayPlan, ...] = ()
    days: int = 0
    servings: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": [d.to_dict() for d in self.plan],
            "days": self.days,
            "servings": self.servings,
        }
