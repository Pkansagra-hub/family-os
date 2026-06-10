"""Static catalog of the built-in family connector definitions.

This module is the single import-time source of the family
:class:`~k1.tools.family.definition.ToolDefinition` objects.  It exists so
that import-time consumers -- notably
:mod:`k1.concierge.prompt.back_profiles` -- can enumerate connectors
*generically* (data-driven) instead of hardcoding a per-domain list or
depending on runtime registration order.

Adding a new family connector is a one-line append here; no consumer needs to
learn its domain.  Whether a connector contributes a Back execution profile is
decided by the connector itself via
``ToolDefinition.back_execution_profile`` -- not by this catalog and not by any
downstream router.
"""

from __future__ import annotations

from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.definition import ToolDefinition
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION

FAMILY_TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    CALENDAR_DEFINITION,
    TASKS_DEFINITION,
    REMINDERS_DEFINITION,
    CHORES_DEFINITION,
    SHOPPING_DEFINITION,
)

__all__ = ["FAMILY_TOOL_DEFINITIONS"]
