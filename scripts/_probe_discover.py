"""Show exactly what Back sees: all registered capability names."""

from k1.fabric.manifest_translator import register_definition
from k1.fabric.core.registry import CapabilityRegistry
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION

registry = CapabilityRegistry()
total = 0
all_defs = [
    ("calendar", CALENDAR_DEFINITION),
    ("tasks", TASKS_DEFINITION),
    ("reminders", REMINDERS_DEFINITION),
    ("chores", CHORES_DEFINITION),
    ("shopping", SHOPPING_DEFINITION),
]
for name, defn in all_defs:
    names = register_definition(defn, registry)
    total += len(names)
    print(
        f"{name:10s}: {len(names):2d} caps  "
        f"domain={defn.domain_tags}  "
        f"activity_profile={defn.activity_profile}  "
        f"back_exec={defn.back_execution_profile}"
    )
    for n in names:
        print(f"            {n}")

print()
print(f"Total executable capabilities: {total}")
print("All are CapabilityContracts with domain=['family', ...]")
print("PromptContracts EXCLUDED from discover_capabilities (retrieval_engine.py:294)")
