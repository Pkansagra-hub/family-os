# Whiteboard — Native Family Apps (The Moat Layer)

> **Status**: Design — pre-implementation. Drives **M15** in [KERNEL_BOOTUP_PLAN.md](../plans/KERNEL_BOOTUP_PLAN.md).
> **Created**: 2026-05-10
> **Scope**: Native FamilyOS apps for daily family coordination. Each app is a CRUD module
> with three input faces (LLM tool-call via Concierge/Fabric, UI form, voice) and one
> cross-family shared truth surface (pseudo-K0 WAL + projections + SSE fan-out).
> **Not in scope**: External IFL adapters (Google Cal, Outlook, etc.) — those are
> *imports/exports* feeding native apps, covered in M17.

---

## 1. The Moat Thesis

> "Google Calendar is one of many feeds flowing INTO the FamilyOS Calendar.
> The shared family layer + parental visibility controls + offline-first + cross-family
> live fan-out is what no calendar app on the market has."

External calendar apps are commodity wrappers around Google's API. They cannot do these
things — and we can:

| Capability | Google Cal | Apple Cal | Cozi | **FamilyOS Native App** |
|---|---|---|---|---|
| Single family-shared truth | per-account | per-account | yes | **yes (K0 family space)** |
| Per-child visibility ACL | no | no | no | **yes (parental control)** |
| Works offline (full CRUD) | partial | partial | no | **yes (K1 local + outbox)** |
| LLM tool-call native | no | no | no | **yes (Fabric capability)** |
| Cross-app coordination | no | no | partial | **yes (one bus, all apps)** |
| Voice / form / chat input | partial | partial | partial | **yes (unified ingress)** |
| Imports from Google/Outlook | n/a | partial | n/a | **yes (feeds, not source)** |
| Provenance per event | n/a | n/a | n/a | **yes (source tag)** |

The five tier-1 apps below are picked because they share ~90% of the CRUD/sync infrastructure.
Build the base once, ship five apps. Build base + visibility + sync + manifest registry first;
each additional app costs ~300 LOC.

---

## 2. The Five Tier-1 Apps

Stabilize these in M15. Each app ships with:

- typed schema (Pydantic)
- projection table in pseudo-K0 SQLite
- `BaseToolService` CRUD subclass
- MCP handler for Concierge LLM tool calls (via `ConnectorHost.dispatch`)
- FastAPI REST routes for UI ingress
- UI manifest endpoint (role-aware, JSON-Forms style)
- import-feed worker stubs (no real external adapters in M15)
- visibility ACL hook
- cross-family SSE emit on `tool_state.changed.v1`

### 2.1 FamilyOS Calendar

The flagship. Drives reminders, presence, planner suggestions.

**Entities**: `CalendarEvent`, `EventAttendee`, `RecurrenceRule`, `ExternalFeed` (Google/Outlook account binding).

**Core operations**:

```
create_event(title, start, end, attendees, visibility, location?, notes?)
update_event(event_id, **patch)
delete_event(event_id)
list_events(start, end, member_filter?, source_filter?)
get_event(event_id)
respond_to_invite(event_id, response: "yes"|"no"|"maybe")

connect_feed(member, source: "google"|"outlook"|"classroom", auth_token)
disconnect_feed(feed_id)
list_feeds(member?)

set_visibility(event_id, visibility, visible_to?)   # parent-only
```

**Why moat**: every family runs on time. Events drive proactive Concierge, kid-aware UI,
shopping suggestions ("you have a birthday party Sat — order cake?").

### 2.2 Tasks

Lightweight to-do with assignment + due dates. Distinct from Chores (chores are *recurring*
and *gamified*; tasks are *one-shot*).

**Entities**: `TaskItem`, `TaskList`, `TaskAttachment`.

**Core operations**:

```
create_task(title, assigned_to, due?, list_id?, priority?, visibility)
update_task(task_id, **patch)
complete_task(task_id)
delete_task(task_id)
list_tasks(assigned_to?, status?, due_before?)
reassign_task(task_id, new_assignee)
```

**Why moat**: "who's picking up Riley today" is the daily-friction question. LLM can read
the calendar, see school ends at 3pm, and auto-create a `pickup_riley` task assigned to
whoever is closest per location service.

### 2.3 Reminders

Tasks with time *or* location triggers + cross-person addressing. "Remind dad to grab
milk on his way home."

**Entities**: `Reminder`, `ReminderTrigger` (time | location_enter | location_leave | event_offset).

**Core operations**:

```
create_reminder(title, recipient, trigger, message?, visibility)
update_reminder(reminder_id, **patch)
snooze_reminder(reminder_id, minutes)
dismiss_reminder(reminder_id)
list_reminders(recipient?, status?)
```

**Why moat**: cross-person reminders are the killer feature. Mom's LLM call creates a
reminder; dad's device fires it locally. No third-party can do this without owning both
devices' OS-level reminder API — FamilyOS does because every member runs K1.

### 2.4 Chores

Recurring family chores + allowance/reward tracking. Native-only (no external import).
This is pure differentiator — there is no "Chores API" to wrap.

**Entities**: `Chore` (template), `ChoreAssignment` (instance), `RewardLedger`.

**Core operations**:

```
create_chore(title, recurrence, default_assignee?, reward?, visibility)
assign_chore(chore_id, member, due)         # auto on recurrence
complete_chore(assignment_id, completed_by, evidence?)
verify_chore(assignment_id, parent)          # parent confirms → unlocks reward
list_chores(member?, status?)
get_reward_balance(member)
redeem_reward(member, amount, reason)
```

**Why moat**: parents can wire reward → screen-time / allowance / experience. LLM can
nudge ("Riley, you have 3 chores left for $5 this week"). No competitor.

### 2.5 Shopping List

Family-shared grocery + general shopping list with meal-plan suggestions and optional
Instacart push.

**Entities**: `ShoppingList`, `ShoppingItem`, `MealPlan` (links → list items).

**Core operations**:

```
create_list(name, visibility)
add_item(list_id, name, qty?, category?, requested_by)
update_item(item_id, **patch)
check_off_item(item_id, checked_by)
delete_item(item_id)
list_items(list_id, status?)
suggest_from_meals(week_start)               # LLM-assisted
push_to_instacart(list_id, account)          # opt-in export (M17 — adapter exists)
```

**Why moat**: shared list that updates live. Mom adds milk on her phone; dad sees it at
the store mid-aisle. LLM auto-adds from meal plan. Cross-family realtime collab.

---

## 3. Three Input Faces, One Truth

Every app is reachable by **three callers**, all hitting the same `BaseToolService` method:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   FACE 1: LLM via Concierge/Fabric                                          │
│   ─────────────────────────────────────                                     │
│   Concierge LLM emits tool_call:                                            │
│     name: "calendar.create_event"                                           │
│     args: {title, start, end, attendees, visibility}                        │
│                                                                             │
│     ↓                                                                       │
│     k1.fabric.invoke("calendar.create_event", args, ctx)                    │
│     ↓                                                                       │
│     BridgeConnectionAdapter → HttpBridgeClient.gateway                      │
│     ↓                                                                       │
│     POST /k0/connector.execute                                              │
│       adapter_id="calendar"                                                 │
│       action="create_event"                                                 │
│       params={...}                                                          │
│       caller_actor_id="mom"   ← from session                                │
│     ↓                                                                       │
│     pseudo-K0 ConnectorHost.dispatch("calendar", "create_event", ...)       │
│     ↓                                                                       │
│     CalendarHandler.call() → CalendarToolService.create_event(...)          │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   FACE 2: UI form / mobile app                                              │
│   ─────────────────────────────────                                         │
│   User taps "+" in calendar app, fills form, taps Save.                     │
│                                                                             │
│     ↓                                                                       │
│     POST /k1/tools/calendar/events       (K1 web shell)                     │
│     ↓                                                                       │
│     k1.tools.family.client.CalendarClient.create_event(...)                 │
│     ↓                                                                       │
│     k1.fabric.invoke("calendar.create_event", ...)   ← SAME PATH AS LLM     │
│     ↓                                                                       │
│     ... → CalendarToolService.create_event(...)                             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   FACE 3: Voice                                                             │
│   ──────────────                                                            │
│   "Hey, add Riley's soccer game Saturday at 10am"                           │
│                                                                             │
│     ↓                                                                       │
│     ASR → Concierge → LLM detects intent → emits tool_call                  │
│     ↓                                                                       │
│     ... → same path as FACE 1                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

ALL THREE FACES → SAME CalendarToolService.create_event(...) ← single ingress
```

**Invariant**: every write to a family app goes through `BaseToolService` (via Fabric).
The UI never writes directly to pseudo-K0 SQLite. The LLM never writes directly. This
guarantees:

- visibility ACL applied uniformly
- WAL emit + SSE fan-out happen on every write
- audit trail captures actor for every change
- one place to add policy enforcement

---

## 4. App Architecture (per app, common shape)

```
scripts/pseudo_k0/tools/
├── __init__.py
├── base.py                ← BaseToolService (CRUD + WAL emit + SSE fan-out + ACL filter)
├── policy.py              ← VisibilityPolicy + default ACL rules
├── manifest.py            ← UIManifest generator (JSON-Forms-style, role-aware)
├── registry.py            ← TOOL_REGISTRY: dict[adapter_id, BaseToolService]
│
├── calendar/
│   ├── __init__.py
│   ├── schema.py          ← Pydantic: CalendarEvent, EventAttendee, RecurrenceRule
│   ├── tables.sql         ← projection DDL: calendar_events, event_attendees, ...
│   ├── service.py         ← CalendarToolService(BaseToolService)
│   ├── handler.py         ← MCP handler (LLM face)
│   ├── routes.py          ← FastAPI router (UI face)
│   ├── manifest.py        ← UI manifest spec (role-aware)
│   └── imports/
│       ├── __init__.py
│       └── feed_worker.py ← per-feed background sync (stub in M15)
│
├── tasks/                 (same shape)
├── reminders/             (same shape)
├── chores/                (same shape)
└── shopping/              (same shape)
```

K1-side client:

```
k1/tools/family/
├── __init__.py
├── client.py              ← FamilyToolClient — wraps /k1/tools/* REST for UI shell
├── manifest_cache.py      ← caches UI manifests pulled from pseudo-K0
└── manifests/             ← optional local cache of role-filtered manifests
```

K1 web ingress:

```
k1/kernel/web/routes/
└── family_tools.py        ← mounts /k1/tools/{adapter_id}/{action} → fabric.invoke()
```

---

## 5. Data Model — Common to All Apps

Every app entity inherits these fields (enforced by `BaseToolService`):

| Field | Type | Purpose |
|---|---|---|
| `id` | str (uuid7) | primary key |
| `space_id` | str | family scope, e.g. `family:smith` |
| `tenant_id` | str | multi-tenant K0 partition |
| `created_by` | str (member_id) | actor |
| `created_at` | int (epoch ms) | |
| `updated_by` | str (member_id) | |
| `updated_at` | int (epoch ms) | |
| `version` | int | optimistic concurrency |
| `source` | enum: `native`\|`google`\|`outlook`\|`teams`\|`classroom`\|`apple`\|`manual_import` | provenance |
| `source_ref` | str? | external id for sync-back (etag, eventId, etc.) |
| `source_account` | str? | which member's external account |
| `visibility` | enum: `family`\|`adults`\|`named`\|`private` | ACL mode |
| `visible_to` | list[member_id] | used when visibility=`named`\|`private` |
| `tags` | list[str] | freeform |
| `metadata` | dict | per-app extensions |

The visibility ACL is applied at **read time** by `BaseToolService.recall()`:

```python
def _apply_visibility_filter(rows, caller_member_id, caller_role):
    visible = []
    for row in rows:
        if row["created_by"] == caller_member_id:
            visible.append(row)                       # always see own
        elif row["visibility"] == "family":
            visible.append(row)
        elif row["visibility"] == "adults" and caller_role in ("parent", "guardian"):
            visible.append(row)
        elif row["visibility"] in ("named", "private") and caller_member_id in row["visible_to"]:
            visible.append(row)
    return visible
```

---

## 6. Visibility Policy

### 6.1 Default rules (shipped in M15)

The defaults live in `policy.py` and run when no per-event override is set:

```yaml
default_visibility_rules:
  - if: source == "native" and creator_role == "parent"
    then: family
  - if: source == "native" and creator_role == "child"
    then: family
  - if: source == "google" and feed_label == "work"
    then: adults
  - if: source == "outlook"
    then: adults
  - if: source == "classroom"
    then: named  # visible_to = [the_child, all_parents]
  - if: title_contains_any: ["doctor", "therapy", "appointment", "medication"]
    then: adults
  - if: source == "google" and feed_label == "personal"
    then: private  # only the importer sees, parent can override
  - default: family
```

### 6.2 Per-event override (UI gear icon)

Parents (and event creators) can override the default by setting `visibility` + `visible_to`
on any event. Kids cannot override their own events' visibility.

### 6.3 Family settings UI (built in M15)

Visibility *policy* (the default rules above) is editable in a **Family Settings** screen,
parent-only:

```
[Family Settings → Visibility]

Imported feeds default to:
  Google (work calendar)        [Adults only ▼]
  Google (personal calendar)    [Private to me ▼]
  Outlook                       [Adults only ▼]
  Microsoft Teams               [Adults only ▼]
  Google Classroom              [Named child + parents ▼]
  Apple Calendar                [Adults only ▼]

Sensitive keywords (auto-redact to adults-only):
  [doctor] [therapy] [appointment] [medication] [+ add]

Kids can:
  ☑ Create events visible to family
  ☐ See parents' personal calendar
  ☐ Override visibility on their own events
  ☑ Mark chores complete
  ☐ Redeem rewards without parent approval
```

The settings page POSTs to `POST /k1/tools/family_settings/visibility_policy` which routes
through Fabric to a `family_settings` adapter in pseudo-K0. Stored in
`family_settings.visibility_policy` table, scoped by `space_id`.

---

## 7. UI Manifest — Generic Renderer Contract

Every app exposes:

```
GET /k1/tools/{adapter_id}/manifest?role={parent|child|guardian}
```

Returns a JSON-Forms-style manifest that K1's web/mobile shell uses to render the app
generically. Same renderer handles all five apps; only the manifest changes.

Example for Calendar (parent role):

```json
{
  "adapter_id": "calendar",
  "version": "1.0",
  "title": "Family Calendar",
  "icon": "calendar",
  "role": "parent",
  "actions": {
    "create_event": {
      "label": "New event",
      "primary": true,
      "form": {
        "fields": [
          {"name": "title",      "type": "string",   "required": true},
          {"name": "start",      "type": "datetime", "required": true},
          {"name": "end",        "type": "datetime", "required": true},
          {"name": "attendees",  "type": "member_multi", "required": false},
          {"name": "location",   "type": "string"},
          {"name": "notes",      "type": "text"},
          {"name": "visibility", "type": "enum",
           "options": ["family","adults","named","private"],
           "default": "family"}
        ]
      }
    },
    "set_visibility": {
      "label": "Change visibility",
      "form": {
        "fields": [
          {"name": "visibility", "type": "enum",
           "options": ["family","adults","named","private"]},
          {"name": "visible_to", "type": "member_multi",
           "show_when": "visibility in ['named','private']"}
        ]
      },
      "context": "per_event_gear_icon"
    }
  },
  "views": {
    "month": {"layout": "calendar_month", "shows": ["all_events"]},
    "week":  {"layout": "calendar_week",  "shows": ["all_events"]},
    "day":   {"layout": "calendar_day",   "shows": ["all_events"]},
    "list":  {"layout": "event_list",     "shows": ["upcoming_events"]}
  },
  "filters": {
    "by_member":   {"type": "member_multi"},
    "by_source":   {"type": "enum_multi",
                    "options": ["native","google","outlook","classroom","apple"]},
    "by_visibility": {"type": "enum_multi",
                      "options": ["family","adults","named","private"]}
  }
}
```

Same endpoint for `role=child` strips the `set_visibility` action, hides the
`visibility` form field (defaults to `family`), removes the `by_visibility` filter,
and excludes `adults`-tagged events from views.

---

## 8. LLM Capability Spec — Auto-Generated from Same Manifest

The Fabric capability registry is auto-populated from the same manifest at startup:

```python
# k1/fabric/manifest_translator.py (already exists per architecture)
for action_name, action_def in manifest["actions"].items():
    fabric.register(FabricToolContract(
        name=f"{adapter_id}.{action_name}",
        description=action_def.get("description", action_def["label"]),
        provider_type=BRIDGE,
        safety_band_min=action_def.get("safety_band", "AMBER"),
        required_inputs=[
            {"name": f["name"], "type": f["type"], "required": f.get("required", False)}
            for f in action_def["form"]["fields"]
        ],
        output_schema=action_def.get("output", {}),
    ))
```

So the Concierge LLM sees:

```
Available tools:
  calendar.create_event(title: str, start: datetime, end: datetime, ...)
  calendar.list_events(start: datetime, end: datetime, member_filter?: list[str])
  tasks.create_task(title: str, assigned_to: str, due?: datetime, ...)
  reminders.create_reminder(title: str, recipient: str, trigger: ReminderTrigger, ...)
  chores.complete_chore(assignment_id: str, evidence?: str)
  shopping.add_item(list_id: str, name: str, qty?: int)
  ...
```

One source of truth (manifest) → three consumers (UI renderer, LLM tool registry, REST
API docs).

---

## 9. Cross-Family Live Sync

Every write through `BaseToolService.write_*()` does:

```python
def write_one(self, op, entity, actor_member_id):
    # 1. Apply default visibility (if not explicitly set)
    entity.visibility = self.policy.apply_default(entity, actor_role)

    # 2. Persist to projection table
    row_id = self.store.upsert(entity)

    # 3. Emit to K0 WAL (via /k0/command.submit) — durable audit
    self.bridge.command.submit(Envelope(
        topic=f"{self.adapter_id}.{op}.v1",
        space_id=entity.space_id,
        actor=actor_member_id,
        payload=entity.model_dump(),
    ))

    # 4. Fan-out SSE event on tool_state.changed.v1
    self.sse.emit(
        topic="tool_state.changed.v1",
        space_id=entity.space_id,
        payload={
            "tool":      self.adapter_id,
            "op":        op,
            "entity_id": entity.id,
            "version":   entity.version,
            "visibility_hint": entity.visibility,
        },
    )
```

Every family K1 (mom's, dad's, kids' devices) is subscribed to SSE for its family space.
On `tool_state.changed.v1` arrival:

1. K1 sees `tool=calendar`, `op=create_event`
2. Refreshes calendar projection by calling `list_events(...)` — recall applies the
   per-member ACL automatically
3. UI shell re-renders the calendar view

Latency target: < 2s mom-write → dad-render on same LAN.

---

## 10. Import Feeds (Stubs in M15, Full in M17)

M15 ships the *plumbing*; M17 ships the actual Google/Outlook/Classroom adapters.

Each feed worker is a per-`(member, source)` background task:

```python
class GoogleCalendarFeedWorker:
    """Pulls events from one member's Google Calendar into FamilyOS Calendar."""

    member_id: str
    google_account: str
    sync_token: str | None
    poll_interval_s: int = 60

    async def run(self):
        while True:
            events = await ifl_invoke(
                "tool.read.calendar.google.list_events",
                params={"sync_token": self.sync_token, "account": self.google_account},
            )
            for ev in events.delta:
                ext = CalendarEvent.from_google(ev)
                ext.source = "google"
                ext.source_ref = ev["id"]
                ext.source_account = self.google_account
                ext.created_by = self.member_id
                ext.visibility = None  # let policy decide
                self.service.upsert(ext, actor_member_id=self.member_id)
            self.sync_token = events.next_sync_token
            await asyncio.sleep(self.poll_interval_s)
```

The IFL adapter (`tool.read.calendar.google.list_events`) is the *external* call — it
goes out through Bridge `ConnectorGateway` → company-hosted Google adapter. That whole
side is **M17**.

In M15, feed workers are scaffolded but disabled by default; `list_feeds()` returns
empty; `connect_feed()` stores the binding but doesn't start the worker.

---

## 11. Permissions — Three-Layer Defense

| Layer | Enforced by | Checks |
|---|---|---|
| **Bridge band gate** | `ConnectorGateway` | tool action's `safety_band_min` ≤ caller's max band |
| **Role gate** | `BaseToolService` action dispatch | role (`parent`\|`child`\|`guardian`) allowed for action |
| **Per-event ACL** | `BaseToolService.recall()` filter | `visibility` + `visible_to` vs caller `member_id` |

Bands and roles are static config (FamilyProfile, M13). The per-event ACL is dynamic
(parent can change visibility on any event after the fact).

Examples:

- `calendar.set_visibility` action → `role: parent` only
- `chores.verify_chore` action → `role: parent` only
- `chores.complete_chore` action → any role (kid can mark own done)
- `reminders.create_reminder` action → any role, but `recipient != self` requires `role: parent`
- `family_settings.update_visibility_policy` action → `role: parent` only

---

## 12. M15 Build Order (high-level — full step-by-step in KERNEL_BOOTUP_PLAN.md M15)

```
Step 1:  BaseToolService + WAL/SSE emit infrastructure
Step 2:  VisibilityPolicy + default rules
Step 3:  Manifest registry + role-aware filter
Step 4:  Tool registry + ConnectorHost handler factory
Step 5:  Calendar app (schema, table, service, handler, routes, manifest)
Step 6:  Tasks app (same shape)
Step 7:  Reminders app
Step 8:  Chores app
Step 9:  Shopping List app
Step 10: family_settings adapter (visibility policy CRUD)
Step 11: K1 FamilyToolClient + manifest cache
Step 12: K1 web routes (/k1/tools/{adapter_id}/{action})
Step 13: Fabric auto-registration from manifests at startup
Step 14: SSE subscription + tool refresh on tool_state.changed.v1
Step 15: Feed worker scaffolding (disabled by default)
Step 16: Tests (per-tool CRUD, ACL, SSE fan-out, manifest role-filter, settings)
Step 17: Pre-flight checks
Step 18: Wire FamilyDataSeeder (M13) to also seed Calendar/Tasks demo entries
Step 19: Smoke test: mom creates event on web → dad's web shows it via SSE
Step 20: Smoke test: Concierge LLM creates calendar event via tool call
```

---

## 13. Boundaries & Anti-Goals

### In scope for M15

- Five tier-1 apps with full CRUD + ACL + sync + manifest + UI manifest endpoint
- Family settings UI for visibility policy (parent-only)
- K1 client wrapper + manifest cache
- Cross-family SSE fan-out using existing `tool_state.changed.v1`
- Fabric auto-registration of every action as a tool capability
- Per-event visibility override (gear icon on every entity)
- Feed worker plumbing (no actual external adapters)

### Out of scope for M15

- Real Google/Outlook/Classroom adapters → **M17** (separate IFL adapter milestone)
- Budget/Finance app → **M16** (heavier compliance, OAuth complexity)
- School / Health / Documents / Contacts / Location / Photos apps → **M18+**
- WebRTC P2P sync (LAN-only mDNS used until then) → post-v2
- Multi-tenancy admin UI (per-family billing, etc.) → operational milestone

### Anti-goals (explicit)

- **NOT** wrapping Google Calendar as the primary app. Google is a feed, not the source.
- **NOT** stdio MCP subprocesses per tool (M14's ConnectorHost is in-process, much faster).
- **NOT** building a generic CRUD framework — `BaseToolService` is shared but small (~200 LOC).
- **NOT** building real-time CRDT merge in M15 — LWW on `(entity_id, version)` is enough
  (cross-family P07 CRDT is K0's job, not M15's).
- **NOT** building a "tool marketplace" UI. M15 ships the 5 native apps. External
  marketplace adapters are M17+.

---

## 14. Relationship to Other Milestones

```
                    M12  Web Coordinator   ──┐
                                              ├─► serves /k1/tools/* routes
                                              │
                    M13  FamilyProfile     ──┤   member_id, role drive ACL
                                              │
                    M14  pseudo-K0         ──┤   ConnectorHost hosts every app handler
                          + ConnectorHost   ─┤   command.submit → WAL
                          + LiveBridge     ──┘   query.recall → projections
                                              │
                  ┌─►  M15  Native Family Apps  ◄──── this whiteboard
                  │       (5 tier-1 apps)
                  │
                  ▼
                M16  Budget app + Plaid adapter
                M17  IFL adapters (Google Cal, Outlook, Classroom, ...)
                M18  Health, School, Documents apps
                M19  Settings UI polish + marketplace UX
```

---

## 15. Open Questions (resolved in M15 plan)

| # | Question | Decision |
|---|---|---|
| Q1 | Tier-1 roster | Calendar, Tasks, Reminders, Chores, Shopping List |
| Q2 | External strategy | (c) FamilyOS-native first; imports as feeds; opt-in export |
| Q3 | SSE topic | single `tool_state.changed.v1` |
| Q4 | UI render | JSON-Forms-style manifest per role |
| Q5 | Input path | all writes via Fabric/ConnectorHost (LLM + UI + voice) |
| Q6 | Storage | WAL + typed projection tables |
| Q7 | Permissions | three-layer: band + role + per-event ACL |
| Q8 | M11 fate | M15 supersedes M11 |
| Q9 | Visibility policy authoring | (b) Family Settings UI in M15 |
| Q10 | CRDT for cross-family | LWW on `(entity_id, version)`; full CRDT deferred |
| Q11 | Per-tool SSE topic? | No — single topic with `{tool, op, entity_id}` payload |
| Q12 | Marketplace UI? | Out of scope for M15 |

---

## 16. Acceptance Criteria

M15 is done when **all** of these pass:

1. `python -m scripts.pseudo_k0` boots with 5 tool services + `family_settings` registered
2. `GET /k1/tools/calendar/manifest?role=parent` returns full manifest with visibility actions
3. `GET /k1/tools/calendar/manifest?role=child` returns filtered manifest (no visibility ops)
4. `POST /k1/tools/calendar/create_event` (UI face) writes WAL + projection + SSE
5. Concierge LLM `tool_call("calendar.create_event", ...)` writes via Fabric path → same result
6. Mom's K1 creates event → dad's K1 receives `tool_state.changed.v1` within 2s
7. Visibility ACL: parent sees `adults` events; child does not see same events
8. Per-event override: parent changes event visibility from `family` to `named[mom,dad]`
9. Family Settings UI updates `visibility_policy`; new imports use new defaults
10. Fabric registry contains all 5 apps' actions (verifiable via `fabric.list_capabilities()`)
11. All 5 apps pass their CRUD + ACL + manifest test suites (target: 60+ tests)
12. Seed data (M13) populates Calendar (Riley soccer, family dinner) + Chores (Riley vacuum)

---

> **Next step**: write M15 in [KERNEL_BOOTUP_PLAN.md](../plans/KERNEL_BOOTUP_PLAN.md)
> with the same developer-grade rigor as M12/M13/M14 — full source for
> `BaseToolService`, `VisibilityPolicy`, all 5 tool services, K1 client, web routes,
> tests, pre-flight checks, and the 20-step implementation order.
