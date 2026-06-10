# Front LLM → K1 Read Surface (`lookup`)

> **Status:** Design whiteboard — not yet implemented.
> **Scope:** A new Front tool that answers read-only K1 state queries ("how does my day look?", "what's happening this week?", future: "is the door locked?", "what's the Tesla charge?").
> **Predecessor:** Phase 1 (GATE-P1) + Phase 1.1 (GATE-P1.1 — family tool constitutions).
> **Companion:** `recall_memories` (K0 deep memory — past/context/history).

---

## 1. Motivation

### The problem

When a user asks "how does my day look?", the current path is:

```
Front LLM → dispatch_task → Back → resolve_situation → 13-step verdict cascade →
  3-pass binder → 4 separate connector reads → assemble → Back reasons → Front presents
```

That is heavy machinery for a **pure read with no mutation intent**. Back's value is write reasoning — constitution enforcement, conflict detection, HIL gates, mutation sequencing. For a read-only aggregation across 4 connectors, Back adds latency and token cost with zero architectural benefit.

### The solution

A new Front tool — `lookup` — that bypasses Back entirely for pre-composed read aggregations. It dispatches directly to K1 Fabric for N parallel connector reads, merges results, and returns structured JSON. Front's LLM handles conversational formatting.

### The three-verb mental model

| Verb | Tool | Kernel | Time | Purpose |
|---|---|---|---|---|
| **Remember** | `recall_memories` | K0 via Bridge | Past | Deep memory, context, history, patterns |
| **Look up** | `lookup` | K1 via Fabric | Present | Current state across connectors |
| **Do** | `dispatch_task` → `resolve_situation` | K1 via Fabric | Future | Writes, mutations, constitution enforcement |

Each verb is unambiguous. No overlap. Front's LLM makes 2 decisions — which verb + which selector — not 12.

---

## 2. Tool Surface — What Front LLM Sees

### Schema

```
Tool: lookup

Use when the user wants to know what's happening right now.
Returns events, tasks, reminders, and chores from family tools.

Examples of when to use:
  "How does my day look?"        → lookup(kind="daily_snapshot")
  "What's Riley doing today?"    → lookup(kind="daily_snapshot", person="Riley")
  "What's happening this week?"  → lookup(kind="weekly_overview")
  "Show me Friday"               → lookup(kind="daily_snapshot", date="2026-06-12")
  "What does everyone have today?" → lookup(kind="daily_snapshot", person="everyone")

Do NOT use for:
  "What do you know about..."    → recall_memories (history/context/K0 memory)
  "Add/schedule/create/assign..." → dispatch_task (writes go through resolve_situation)
  "What tools can..."            → discover_capabilities (meta)

How to present results:
  Format the returned JSON conversationally. Group by time of day.
  Mention conflicts between events. Be warm and natural, not robotic.
  If nothing is scheduled, say so reassuringly — "You've got a clear day!"
```

### Parameters

| Parameter | Required | Default | Type | Description |
|---|---|---|---|---|
| `kind` | Yes | — | `"daily_snapshot"` \| `"weekly_overview"` | What time window to query |
| `person` | No | Current user | `string` | Person name or "everyone" |
| `date` | No | Today | `string` (YYYY-MM-DD) | Base date for the snapshot |

That's it. Three parameters. The LLM does NOT specify:

- Which connectors to query (tool knows `daily_snapshot` = calendar+tasks+reminders+chores)
- Query strings per connector (tool builds them from person+date)
- Sort order or grouping (tool's responsibility)

### Return shape

```json
{
  "kind": "daily_snapshot",
  "person": "Riley",
  "date": "2026-06-08",
  "day_of_week": "Monday",
  "events": [
    {
      "title": "Soccer practice",
      "start": "2026-06-08T15:00:00",
      "end": "2026-06-08T17:00:00",
      "location": "Riverside Park",
      "calendar": "Riley's calendar"
    }
  ],
  "tasks": [
    {
      "title": "Math homework - Chapter 12",
      "due": "2026-06-08T20:00:00",
      "priority": "high",
      "status": "pending",
      "assigned_to": "Riley",
      "created_by": "parent"
    }
  ],
  "reminders": [
    {
      "message": "Take allergy medicine",
      "time": "2026-06-08T20:00:00",
      "person": "Riley",
      "event_ref": null
    }
  ],
  "chores": [
    {
      "title": "Vacuum living room",
      "frequency": "every Saturday",
      "next_due": "2026-06-13",
      "reward": "$2.00",
      "assigned_to": "Riley",
      "status": "pending"
    }
  ],
  "empty_slots": [
    {"start": "10:00", "end": "12:00"},
    {"start": "13:00", "end": "15:00"}
  ],
  "conflicts": [],
  "meta": {
    "total_items": 4,
    "connectors_queried": ["family.calendar", "family.tasks", "family.reminders", "family.chores"],
    "query_time_ms": 120
  }
}
```

**Design rules for the return shape:**

1. **Always the same shape** — empty results have `"events": []`, not missing keys. The LLM never checks for key existence.
2. **`empty_slots`** answers "when am I free?" without a second tool call. Computed from event gaps > 30 minutes.
3. **`conflicts`** flags overlapping events. Advisory only — no blocking.
4. **`meta`** is for debugging, not LLM consumption. Front can log it but the LLM ignores it.

### Weekly overview return shape

Same as daily but wrapped in a `days` array:

```json
{
  "kind": "weekly_overview",
  "person": "Riley",
  "week_of": "2026-06-08",
  "days": [
    {
      "date": "2026-06-08",
      "day_of_week": "Monday",
      "events": [...],
      "tasks": [...],
      "reminders": [...],
      "chores": [...],
      "empty_slots": [...],
      "conflicts": [...]
    },
    // ... 6 more days
  ],
  "meta": { ... }
}
```

---

## 3. Behavior — Tool Implementation Contract

### What `lookup` MUST do

1. **Resolve `person`** against household members. "Riley" → person_id. "everyone" → all members.
2. **Resolve `date`** — "today", "tomorrow", "Friday", ISO dates. Default to today in household timezone.
3. **Resolve domain** from active session (e.g., "family", "enterprise", "agriculture").
4. **Discover participating connectors** — query `GlobalProjectionStore` for all connectors in the active domain whose `snapshot_types` includes the requested `kind`. This is dynamic, not hardcoded.
5. **Discover read capabilities** — for each participating connector, find the `invocation_mode=read` capability with `action_name=list` (or the primary read capability).
6. **Dispatch parallel Fabric reads** — one per discovered connector, passing `person` and `date_range` as params.
7. **Merge results** into the standard return shape keyed by `resource_kind`.
8. **Compute `empty_slots`** from time-gapped resources (for snapshot types that include time-based resources).
9. **Detect `conflicts`** — overlapping events or resource-vs-resource time clashes.
10. **Return within 3 seconds** — parallel reads, not sequential. If one connector times out, return partial data with `"partial": true` in meta.

### What `lookup` MUST NOT do

1. **No writes.** Read-only. No constitution enforcement needed.
2. **No `resolve_situation`.** This is NOT Back's resolver. No intent ambiguity, no 13-step cascade.
3. **No HIL gates.** Reads don't need human confirmation.
4. **No K0 calls.** This is K1 current state. K0 enrichment is v2.
5. **No hardcoded connector lists.** The tool discovers participating connectors from `GlobalProjectionStore` based on `snapshot_types`. Works for ANY domain — family, enterprise, government, agriculture, healthcare, bankos, finaincos, govos, agrios.

### Error handling

| Scenario | Behavior |
|---|---|
| Person not found | Return empty with `"person_resolved": false` in meta |
| Date invalid | Return `status: "error"` with message |
| One connector times out | Return partial data from other connectors, flag `"partial": true` |
| All connectors fail | Return empty with `status: "error"` and diagnostic message |
| No Fabric wired (POC) | Return empty with `status: "unavailable"` |

### Idempotency

Not needed. Pure reads, no side effects. Different from `resolve_situation` which needs idempotency because it gates writes.

---

## 4. Architecture — Dynamic, Domain-Agnostic Discovery

### Design principle: connectors self-declare snapshot participation

The tool does NOT know what connectors exist. It queries the store. This works for ANY domain instantiated on K1 — family, enterprise, government, agriculture, healthcare, or future domains (bankos, finaincos, govos, agrios).

### Prerequisite: `snapshot_types` field on connector manifests

Each connector declares which snapshot types it participates in via a new optional field. Per the connector onboarding docs (`connector_onboarding_familyos.md` §1.1), connectors already declare `resource_kinds`, `ontology`, `constitution`, `policy_declarations`. `snapshot_types` is one more self-describing field.

```yaml
# In ConnectorDefinition / connector manifest:
snapshot_types:                          # NEW — optional, empty = no participation
  - "daily_snapshot"                     # Appears in "how does my day look"
  - "weekly_overview"                    # Appears in "what's happening this week"
  # - "sprint_status"                    # Future: enterprise sprint snapshot
  # - "farm_status"                      # Future: agriculture farm status
```

Connectors without this field (or with an empty list) do NOT appear in any snapshot. Examples:

| Connector | `snapshot_types` | Why |
|---|---|---|
| `family.calendar` | `["daily_snapshot", "weekly_overview"]` | Core daily awareness |
| `family.tasks` | `["daily_snapshot", "weekly_overview"]` | Core daily awareness |
| `family.reminders` | `["daily_snapshot", "weekly_overview"]` | Core daily awareness |
| `family.chores` | `["daily_snapshot", "weekly_overview"]` | Core daily awareness |
| `family.documents` | (none) | Not time-sensitive, not daily snapshot material |
| `family.budgets` | (none) | Not time-sensitive |
| `enterprise.bug_tracker` | `["sprint_status"]` | Only appears in sprint snapshots, not daily |
| `enterprise.oncall_schedule` | `["daily_snapshot"]` | On-call is daily awareness |
| `agriculture.field_planner` | `["daily_snapshot", "farm_status"]` | Field planning is daily |
| `healthcare.appointments` | `["daily_snapshot", "weekly_overview"]` | Appointments are daily awareness |

This is the same pattern as `resource_connector_edges` and `companion_resource_roles` — connectors declare their own relationships; the kernel queries, doesn't hardcode.

### Data flow

```
lookup(kind="daily_snapshot", person="Riley", date="2026-06-08")
  │
  ├─ 1. Resolve domain from active session → "family"
  │      Resolve person → person_id via LPS.household_members
  │      Resolve date → ISO date range
  │
  ├─ 2. Stage 1 — GPS: discover ELIGIBLE connectors
  │      SELECT c.connector_id, c.resource_kinds, c.snapshot_types_json,
  │             cap.capability_name, cap.action_name
  │      FROM connectors c
  │      JOIN capabilities cap ON c.connector_id = cap.connector_id
  │      WHERE c.admission_verdict = 'admitted'
  │        AND c.connector_id LIKE 'family.%'           -- domain filter
  │        AND c.snapshot_types_json LIKE '%daily_snapshot%'
  │        AND cap.invocation_mode = 'read'
  │        AND cap.record_type = 'executable_capability'
  │      → returns: 10 connectors (GPS has all 10 family connectors)
  │
  ├─ 3. Stage 2 — LPS: filter to CONNECTED only
  │      SELECT connector_id, resource_id, resource_kind
  │      FROM connected_resources
  │      WHERE actor_id = user_id
  │        AND connector_id IN (eligible_from_stage1)
  │        AND status = 'active'
  │      → returns: 4 connectors (user connected calendar, tasks, chores, reminders)
  │
  ├─ 4. For each CONNECTED connector, build Fabric read request:
  │      fabric.invoke_capability(
  │          capability_name=cap.capability_name,
  │          params={resource_id: cr.resource_id, time_min: date_start, time_max: date_end}
  │      )
  │
  ├─ 5. asyncio.gather(all_reads) → results[]
  │      (reads execute through CapabilityFabric's 9-step pipeline:
  │       resolve → gate → context → instantiate → execute → validate → emit)
  │
  ├─ 6. Merge by resource_kind into standard return shape
  │
  ├─ 7. Compute empty_slots from time-gapped resources
  │      Compute conflicts from overlapping resources
  │
  └─ 8. Return standard shape
```

### Key architectural decisions

1. **Domain-agnostic.** The tool queries the store for the ACTIVE session's domain. If the session is `enterprise`, it discovers enterprise connectors. If `agriculture`, agriculture connectors. No domain-specific code paths.

2. **Connector metadata drives participation.** `snapshot_types` is a connector-level declaration, like `resource_kinds` and `companion_resource_roles`. The kernel queries; the connector declares.

3. **GlobalProjectionStore is the registry.** No separate snapshot template file. The store already has connectors, capabilities, resource_kinds, ontology. One more JSON column is all it takes.

4. **Parallel reads, not sequential.** `asyncio.gather()` all reads. 3-second total timeout. Partial results on timeout.

5. **Same closure pattern as `recall_memories`.** `build_lookup_fn(fabric_port, global_store, local_store)` — the closure captures Fabric (for dispatching reads), GlobalProjectionStore (for discovering eligible connectors across all domains), and LocalProjectionStore (for filtering to connected resources). Both stores are already available at P4 wiring time.

6. **No new connector.** `lookup` is a Front tool, not a connector. It's the symmetric counterpart to `recall_memories` — one queries K0 (past), one queries K1 (present).

### What we deliberately do NOT build

- ❌ A new connector registered in `GlobalProjectionStore`
- ❌ Hardcoded connector lists for any domain
- ❌ Domain-specific snapshot logic
- ❌ `resolve_situation` integration
- ❌ K0 Bridge integration (v2)
- ❌ Caching layer (v2)

### Storage change: `connectors` table

Add one JSON column to the existing `connectors` table:

```sql
ALTER TABLE connectors ADD COLUMN snapshot_types_json TEXT NOT NULL DEFAULT '[]';
```

The `ConnectorRecord` and `ConnectorDefinition` dataclasses gain one optional field (defaults to empty list). The `ToolDefinition` (family tools, `definition.py`) gains one optional field. Backward compatible — existing connectors without the field simply don't participate in snapshots.

### Pattern: mirror `recall_memories`

```
recall_memories                          lookup
─────────────────────                    ─────────────────────
k1/concierge/adapters/recall_memory.py   k1/concierge/adapters/lookup.py
  build_recall_fn(bridge_client)           build_lookup_fn(fabric_port, global_store, local_store)
  RecallMemoryAdapter                      LookupAdapter
  ↓ K0 via Bridge                          ↓ K1 via Fabric + GPS + LPS

k1/concierge/tools/schemas_front.py      k1/concierge/tools/schemas_front.py
  RECALL_MEMORY_SCHEMA                     LOOKUP_SCHEMA

k1/concierge/tools/implementations.py    k1/concierge/tools/implementations.py
  execute_recall_memory                    execute_lookup

k1/kernel/service.py (P4)                k1/kernel/service.py (P4)
  memory=RecallMemoryAdapter(...)          lookup=LookupAdapter(..., global_store=..., local_store=...)
```

### `build_lookup_fn` closure signature

```python
def build_lookup_fn(
    fabric_port: Any | None,           # IDispatchPort — dispatches Fabric reads via invoke_capability
    global_store: Any | None,          # GlobalProjectionStore — discovers eligible connectors (all 500+)
    local_store: Any | None,           # LocalProjectionStore — filters to connected resources (this user's ~10)
    *,
    space_id: str = "default",
    domain: str = "family",            # Default domain; overridden per-session
) -> Callable[..., Any]:
    """Build a lookup closure with two-stage GPS→LPS discovery.

    Stage 1 (GPS): Query global_store for connectors in the active domain
    with matching snapshot_types. This is the 'eligible' set — all connectors
    that COULD participate.

    Stage 2 (LPS): Query local_store.connected_resources to filter eligible
    connectors down to what THIS user has actually connected. This prevents
    querying connectors the user hasn't set up.

    Then dispatches parallel Fabric reads via fabric_port.invoke_capability()
    for each connected connector. Reads execute through CapabilityFabric's
    9-step pipeline (resolve → gate → context → instantiate → execute →
    validate → emit).

    The closure is domain-agnostic — works for family, enterprise,
    government, agriculture, healthcare, and future domains.

    Returns:
        async def _lookup(kind, person, date) -> dict
    """
```

---

## 6. Future Selectors — Zero Code Changes in `lookup`

The `kind` parameter is the extension point. New snapshot types are supported when connector authors add them to their connector's `snapshot_types` list. **No code changes needed in `lookup`** — the tool discovers participating connectors dynamically from `GlobalProjectionStore`, then filters to connected via `LocalProjectionStore`.

### v1 (this design)

| `kind` | Which connectors participate |
|---|---|
| `daily_snapshot` | All connectors with `snapshot_types` containing `"daily_snapshot"` |
| `weekly_overview` | All connectors with `snapshot_types` containing `"weekly_overview"` |

Example for `family` domain: calendar, tasks, reminders, chores all declare both types. Documents, budgets, habits don't — they don't appear.

### v2 (planned, not designed)

Each new `kind` requires **zero code changes in `lookup`**. Connector authors add the `kind` to their `snapshot_types` list:

| `kind` | Deployment | Example connectors that declare it |
|---|---|---|
| `sprint_status` | Enterprise domain | `enterprise.bug_tracker`, `enterprise.feature_tracker`, `enterprise.oncall_schedule` |
| `farm_status` | Agriculture domain | `agriculture.field_planner`, `agriculture.livestock`, `agriculture.equipment_log`, `agriculture.irrigation` |
| `home_status` | IFL devices | `ifl.home.hue`, `ifl.home.nest`, `ifl.home.ring`, `ifl.home.smart_lock` |
| `vehicle_status` | IFL devices | `ifl.transport.tesla`, `ifl.transport.uber` |
| `finance_snapshot` | IFL devices | `ifl.finance.chase`, `ifl.finance.plaid` |
| `health_snapshot` | IFL devices | `ifl.health.fitbit`, `ifl.health.apple_health`, `ifl.health.garmin` |

### K0 enrichment (v2)

Add optional K0 context via `k0_context: bool = False` parameter. When true, the tool also calls `recall_memories` for the person and injects relevant episodic/semantic context under a `k0_context` key.

---

## 7. What This Tool Is NOT

| NOT | Why | Use instead |
|---|---|---|
| A write tool | No mutations, no side effects | `dispatch_task` → `resolve_situation` |
| A K0 memory search | No deep history, semantic search, episodic patterns | `recall_memories` |
| A capability discovery tool | No FTS5 search, no ontology traversal | `discover_capabilities` |
| A replacement for Back | No intent reasoning, no constitution enforcement | `resolve_situation` |
| A single-connector read | If user says "show me Riley's calendar" that's `invoke_capability`, not `lookup` | `invoke_capability` |

---

## 8. File Changes

### New files

| File | Purpose |
|---|---|
| `k1/concierge/adapters/lookup.py` | `LookupAdapter` + `build_lookup_fn()` closure |
| `k1/docs/future_work/front_llm_read_k1surface.md` | This document |

### Modified files

| File | Change |
|---|---|
| `k1/concierge/tools/schemas_front.py` | Add `LOOKUP_SCHEMA` with 3 params |
| `k1/concierge/tools/implementations.py` | Add `execute_lookup` (registered, delegates to `ctx.lookup_fn`) |
| `k1/concierge/tools/dispatcher.py` | Add `lookup` to `_FRONT_SIMPLE` allowlist |
| `k1/concierge/factory.py` | `PortBundle` gains `lookup` attribute |
| `k1/concierge/tools/implementations.py` | `ToolContext` gains `lookup_fn` attribute |
| `k1/kernel/service.py` | P4: `LookupAdapter(build_lookup_fn(fabric=session_fabric, global_store=gps, local_store=lps))` |
| `k1/fabric/stores/global_projection_store.py` | `ConnectorRecord` gains `snapshot_types: list[str]` (default `[]`) |
| `k1/fabric/connectors/definition.py` | `ConnectorDefinition` gains `snapshot_types` optional field |
| `k1/tools/family/definition.py` | `ToolDefinition` gains `snapshot_types` optional field |
| `k1/fabric/manifest_translator.py` | `register_definition_to_store()` maps `snapshot_types` |
| `k1/fabric/docs/connector_onboarding_familyos.md` | Document `snapshot_types` in §1.1 |
| `k1/fabric/docs/connector_development_external.md` | Document `snapshot_types` for external devs |
| `k1/fabric/docs/phase1_implementation_plan.md` | Add Epic 15 |

---

## 9. Open Questions

| # | Question | Status |
|---|---|---|
| 1 | Should `everyone` return per-person breakdowns or a merged household view? | **Open** — per-person is more useful for "what does everyone have today?" |
| 2 | Should `weekly_overview` exclude weekends if the household config says so? | **Open** — defer to v2 household config |
| 3 | Should the tool accept a `connectors` filter? (e.g., "just show me tasks") | **No for v1** — that's `invoke_capability`, not `lookup` |
| 4 | Timezone — household config or device context? | **Household config** — already available via SpatialHandle |
| 5 | What happens when a connector doesn't exist yet? (pre-Phase 1) | Return empty array for that connector, flag `"connector_missing"` in meta |

---

## 10. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-06-08 | Tool named `lookup` | Single word, natural language, scales to all domains |
| 2026-06-08 | Separate tool from `recall_memories` — not overloaded | Different destinations (K0 vs K1), different return shapes, different LLM triggers. Overloading would confuse Front LLM |
| 2026-06-08 | Three-verb model: remember / look up / do | Clean separation: K0 past, K1 present, K1 future |
| 2026-06-08 | Structured JSON return, not natural language | Let Front LLM do conversational formatting; tool returns data |
| 2026-06-08 | No `resolve_situation` for reads | Heavy machinery not needed for pre-composed aggregations |
| 2026-06-08 | K1 only for v1 (no K0 enrichment) | Ship the 90% use case first; K0 context is v2 |
| 2026-06-08 | Closure pattern matching `build_recall_fn` | Consistency — same adapter pattern, different destination |
| 2026-06-08 | Connectors self-declare `snapshot_types` — no hardcoded lists | Kernel-level engineering: works for ANY domain (bankos, finaincos, govos, agrios, enterpriseos). Connectors already self-declare resource_kinds, ontology, companions — snapshot participation is one more self-describing field. New snapshot types require zero code changes in `lookup`. |
| 2026-06-08 | `lookup` queries GlobalProjectionStore dynamically | The store is the registry. No separate snapshot template file. One JSON column (`snapshot_types_json`) on the existing `connectors` table. |
