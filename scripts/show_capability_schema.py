"""Show what discover_capabilities returns for native family app actions."""

from k1.fabric.manifest_translator import build_contract
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION

for defn in [
    CALENDAR_DEFINITION,
    REMINDERS_DEFINITION,
    TASKS_DEFINITION,
    CHORES_DEFINITION,
    SHOPPING_DEFINITION,
]:
    for action in defn.actions:
        c = build_contract(defn, action)
        ti = (c.tool_instructions or "")[:120]
        print(f"=== {c.name} ===")
        print(f"  description:     {c.description}")
        print(f"  prompt_template: {c.prompt_template}")
        print(f"  activity_profile:{c.activity_profile}")
        print(f"  tool_instruct:   {ti}")
        print(f"  required_inputs: {[i.name for i in c.required_inputs]}")
        print(f"  optional_inputs: {[i.name for i in c.optional_inputs]}")
        print(f"  limitations:     {c.limitations[:2]}")
        print(f"  safety_band_min: {c.safety_band_min}")
        print()
