"""
Scenario loader -- selects and configures scenarios for benchmark runs.
"""

from __future__ import annotations

from typing import List, Optional

from core.models import Scenario
from scenarios.definitions import get_all_scenarios, get_scenario_by_id


def load_scenarios(
    scenario_ids: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
) -> List[Scenario]:
    """
    Load scenarios by ID list or tag filter.

    Args:
        scenario_ids: List of scenario numbers (1-8). None = all.
        tags: Filter by tag. None = no filter.

    Returns:
        List of Scenario objects.
    """
    if scenario_ids:
        return [get_scenario_by_id(sid) for sid in scenario_ids]

    scenarios = get_all_scenarios()

    if tags:
        scenarios = [s for s in scenarios if any(t in s.tags for t in tags)]

    return scenarios


def list_scenarios() -> List[dict]:
    """Return a summary of all available scenarios."""
    return [
        {
            "id": i + 1,
            "scenario_id": s.id,
            "name": s.name,
            "description": s.description,
            "max_iterations": s.max_iterations,
            "max_tools": s.max_tools,
            "tier": s.tier.value,
            "registry": s.registry,
            "tags": s.tags,
        }
        for i, s in enumerate(get_all_scenarios())
    ]
