"""Safety band invariants for native family tools."""

from __future__ import annotations

from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.family_settings.definition import FAMILY_SETTINGS_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION


def test_all_native_family_actions_are_green() -> None:
    definitions = [
        CALENDAR_DEFINITION,
        CHORES_DEFINITION,
        FAMILY_SETTINGS_DEFINITION,
        REMINDERS_DEFINITION,
        SHOPPING_DEFINITION,
        TASKS_DEFINITION,
    ]

    for definition in definitions:
        for action in definition.actions:
            assert action.min_band == "GREEN", f"{definition.adapter_id}.{action.name}"
