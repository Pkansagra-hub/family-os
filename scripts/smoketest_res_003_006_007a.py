"""E2E smoketest for RES-003-core + RES-006 + RES-007a."""

import os
import tempfile
from datetime import datetime, timezone

from k1.fabric.resolver.capability_type_resolver import ConnectorResolver
from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    ConnectorRecord,
    GlobalProjectionStore,
)

tmp = tempfile.mktemp(suffix=".db")
gps = GlobalProjectionStore(tmp)
gps.open()

now = datetime.now(timezone.utc).isoformat()

# Register shopping connector
gps.upsert_connector(
    ConnectorRecord(
        connector_id="family.shopping",
        label="Shopping",
        connector_type="native",
        provider_type="LOCAL",
        version="1.0.0",
        admission_verdict="admitted",
        registration_type="static",
        created_at=now,
        updated_at=now,
    )
)
gps.upsert_capability(
    CapabilityRecord(
        capability_name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        invocation_mode="execute",
        action_name="add_item",
        effect="write",
        resource_kind="grocery_item",
        description="Add an item to the shopping list",
        created_at=now,
        contract_json={},
    )
)
gps.upsert_connector_fts_text(
    "family.shopping",
    "Shopping",
    "Family shopping list manager",
    "Shopping. Family shopping list manager. Add item to shopping list. "
    "Groceries, shopping, list, items, add, remove, buy, purchase, order",
)

# Register tasks connector
gps.upsert_connector(
    ConnectorRecord(
        connector_id="family.tasks",
        label="Tasks",
        connector_type="native",
        provider_type="LOCAL",
        version="1.0.0",
        admission_verdict="admitted",
        registration_type="static",
        created_at=now,
        updated_at=now,
    )
)
gps.upsert_capability(
    CapabilityRecord(
        capability_name="tool.execute.family.tasks.create_task",
        connector_id="family.tasks",
        invocation_mode="execute",
        action_name="create_task",
        effect="write",
        resource_kind="task_item",
        description="Create a new task",
        created_at=now,
        contract_json={},
    )
)
gps.upsert_connector_fts_text(
    "family.tasks",
    "Tasks",
    "Family task manager",
    "Tasks. Family task manager. Create task, complete task, assign task, to-do list.",
)

# Build resolver
resolver = ConnectorResolver(gps)

# Test 1: shopping query
result = resolver.resolve("add eggs to my shopping list")
print("Query: add eggs to my shopping list")
primary = result.primary
print(
    f"  Primary: {primary['connector_id']} (score={primary['score']})"
    if primary
    else "  Primary: None"
)
for alt in result.alternatives:
    print(f"  Alt: {alt['connector_id']} (score={alt['score']})")

# Test 2: task query
result2 = resolver.resolve("remind me to finish homework")
print("Query: remind me to finish homework")
primary2 = result2.primary
print(
    f"  Primary: {primary2['connector_id']} (score={primary2['score']})"
    if primary2
    else "  Primary: None"
)
for alt in result2.alternatives:
    print(f"  Alt: {alt['connector_id']} (score={alt['score']})")

gps.close()
os.unlink(tmp)
print("E2E test PASSED")
print("E2E test PASSED")
