# Back Tool Contract — Production-Grade POC Design

**Status:** Design document. Component designs are filled incrementally; each component must be proven before production migration begins.
**Purpose:** Design, build, and prove every component of the Back ReAct situated execution loop — end to end, at production standard — before touching the production codebase.
**Source design spine:** [back_tool_contract_whiteboard.md](back_tool_contract_whiteboard.md)
**Implementation skeleton:** [back_tool_contract_developer_implementation_skeleton.md](back_tool_contract_developer_implementation_skeleton.md)

---

## 0. Problem Statement

### The Core Problem

Back currently executes tool calls by discovering capabilities top-K and invoking by name:

```text
discover_capabilities(intent) -> top-K scored records -> capability_name -> invoke_capability -> submit_result
```

This is not sufficient for a production household execution kernel. The problems are:

```text
1. top-K ranking is not execution authority.
   A capability appearing at rank 1 in a semantic search does not mean it is safe, policy-cleared,
   idempotency-tracked, resource-bound, or verified for this actor in this session.

2. The LLM invents resources.
   Without a local-world projection, Back is allowed to assume "Riley's calendar" exists and is writeable.
   If it does not, the invocation fails late or silently.

3. Params are not validated against the actual capability contract before dispatch.
   duration_minutes arrives at a provider that needs end. The call fails, retries, and wastes context.

4. Provider success is not verified completion.
   A successful HTTP 200 from calendar create is not the same as the event existing in the system of record.
   Back calls submit_result(complete) on provider status alone.

5. There is no authority chain.
   No record of which policy authorized the side effect, which binding was chosen, or which verification ran.
   Audit is reconstructed from logs, not from structured evidence attached to the task.

6. Safety band is a string, not a governed contract.
   GREEN/AMBER/RED on a task does not automatically map to connector-specific, operation-specific,
   role-specific policy gates. BTC-004 is the live bug; it silently allows or blocks without evidence.

7. Multi-connector and cross-resource tasks have no plan authority.
   A task that touches calendar + contacts + reminders is dispatched through the same flat
   discover/invoke path. There is no companion resource resolution, dependency sequencing, or
   compensation plan.

8. The LLM can call any discovered capability in any order.
   allowed_next_actions is currently guidance text, not a runtime-enforced dispatch gate.
```

### What We Need To Prove Before Production Migration

The solution is not to patch the current path. The solution is to build a parallel execution authority spine:

```text
Back receives BackTaskEnvelope
  -> builds RequestFrame
  -> calls resolve_situation
  -> Resolver builds CandidateUniverse from local-world projection
  -> Resolver applies policy and binding authority
  -> Resolver returns ResolutionEnvelope + PromptPack
  -> Back acts only through allowed_next_actions
  -> Fabric validates invocation against binding contract and policy gate refs
  -> InvocationObservation is returned to Back
  -> VerificationObservation is produced before completed is legal
  -> Back calls submit_result with structured evidence
```

Every component in this chain needs to be:

```text
designed       : concrete schema, behavior, contracts, and test surface
built          : production-grade implementation, not a mock or stub
proven         : tested against 100 real request scenarios
model-tested   : validated against multiple LLM backends
negative-proved: the failure paths work correctly, not just the happy path
```

Only after each component has been individually proven and end-to-end proven does production migration begin. This document is the design and proof plan for that work.

---

## 1. POC Scope And Graduation Criteria

### What This POC Is

This is a parallel production-grade implementation that:

```text
1. Runs alongside the current kernel, not replacing it yet.
2. Proves every component at scale before any production code changes.
3. Tests against 100 designed request scenarios, covering LOW/MEDIUM/HIGH complexity.
4. Tests against 40 designed connectors, covering native local, bridge-connected, IFL, read-only, and write-capable types.
5. Proves with real LLM backends (Gemini Pro, Gemini Flash, GPT-4o, GPT-4o-mini, Claude Sonnet).
6. Produces structured proof records for every milestone.
7. Produces negative proof: every designed failure path triggers its typed error correctly.
```

### What This POC Is Not

```text
1. Not a mock/stub demo. Canned model responses are rejected by the proof harness.
2. Not a narrow slice showing only the happy path.
3. Not a prototype to be rewritten. Code written here must be promotable to production.
4. Not a single LLM test. Model matrix must cover small, medium, and large model classes.
5. Not allowed to claim projection/resolver/binding work by faking the DB.
```

### Graduation Criteria Per Component

A component is proven and ready for production migration when:

```text
- All relevant request scenarios in the scenario corpus pass its proof assertions.
- All relevant connectors exercise it correctly.
- Negative proof tests demonstrate typed failures for every designed failure path.
- At least two LLM backends pass the component's model-visible seams.
- A ShadowComparisonRecord comparing current path vs new path exists and recommends cutover.
- No raw catalogs, secrets, or full manifests leaked into prompt captures.
- proof_record.all_pass = true across the component's milestone set.
```

---

## 2. Request Scenario Corpus Design

### Overview

The scenario corpus must be designed before implementation. Every component is evaluated against every applicable scenario. Scenarios are the source of truth for what "correct" means.

Design 100 scenarios across these categories:

```text
Tier 1 - Conversational (no execution):       15 scenarios
Tier 2 - Single connector reads:              20 scenarios
Tier 2 - Single connector writes:             25 scenarios
Tier 2 - Prerequisite read + write:           15 scenarios
Tier 2 - Disambiguation and HIL:              10 scenarios
Tier 3 - Multi-connector:                      8 scenarios
Tier 3 - Cross-resource with companions:       5 scenarios
Edge and failure cases:                        2 scenarios (see negative proof)
```

### Scenario Schema

Each scenario is a JSON record:

```json
{
  "scenario_id": "S001",
  "label": "Add family calendar event simple",
  "tier": "tier2",
  "complexity": "LOW",
  "user_phrase": "Add Riley's dentist appointment tomorrow at 5pm for 45 minutes",
  "expected_resource_kinds": ["calendar_event", "household_member"],
  "expected_connectors": ["calendar"],
  "expected_operations": ["list_events", "create_event"],
  "expected_prerequisite_reads": ["list_events"],
  "expected_writes": ["create_event"],
  "expected_verification": "read_after_write",
  "expected_hil": false,
  "expected_disambiguation": false,
  "expected_resolution_verdict": "can_execute_with_prerequisite_read",
  "expected_submit_status": "completed",
  "negative_assertions": [],
  "notes": "duration_minutes must be converted to end before create_event dispatch"
}
```

### Required Scenario Coverage

Every scenario corpus file must cover:

```text
Person reference scenarios:
  S001-S010  Single person, unambiguous
  S011-S015  Person reference ambiguous (two people named Riley)
  S016-S020  No person named, implicit actor scope

Time reference scenarios:
  S021-S030  Concrete time (tomorrow 5pm, Friday 3pm)
  S031-S035  Relative time (in two hours, this weekend)
  S036-S040  Ambiguous time (sometime next week -> needs HIL)

Connector-specific scenarios:
  S041-S055  Calendar (create, list, update, delete, conflict)
  S056-S065  Tasks/reminders (create, complete, due-date)
  S066-S070  Contacts (read, update)
  S071-S075  Notes (create, search, update)

Multi-connector and Tier 3:
  S076-S083  Calendar + contacts (event with participant, resolve contact first)
  S084-S088  Calendar + reminders (create event + add reminder)

Failure and edge:
  S089-S092  Missing required params
  S093-S095  Conflict blocks write
  S096-S098  Stale projection blocks write
  S099       Budget exhausted mid-loop
  S100       Duplicate idempotency key after success
```

### Scenario Store Location

```text
poc/back_tool_contract/scenarios/
  scenario_corpus.json         all 100 scenarios
  scenario_schema.json         schema definition
  scenario_index.json          index by tier, connector, expected_verdict
```

---

## 3. Connector Corpus Design

### Connector Corpus Overview

Design 40 connectors that the POC resolver, binding, and invocation components must handle. These are fixture connectors, not necessarily live external services. They must have real manifests, real schemas, real capability contracts, and real policy declarations. No placeholder-only connectors.

### Connector Categories

```text
Native local (SQLite-backed):                  10 connectors
  calendar, tasks, reminders, notes, contacts
  chores, habits, budgets, shopping, documents

Bridge-connected (local process):              10 connectors
  google_calendar_read, google_calendar_write (future)
  google_tasks, todoist, notion, apple_reminders
  slack_dm, email_send, weather, news_digest

IFL external read-only:                        10 connectors
  school_calendar_read, sports_schedule_read
  doctor_appointment_read, pharmacy_refill_status
  bank_balance_read, credit_score_read
  package_tracking, flight_status
  local_events_read, transit_schedule_read

IFL external write-capable:                     5 connectors
  restaurant_reservation_create, appointment_book
  ticket_purchase, rideshare_book, food_order

System/platform connectors:                     5 connectors
  family_broadcast (announce to all), alert_send
  reminder_fire (system trigger), audit_log_write
  notification_push
```

### Connector Manifest Schema

Each connector must have a production-grade manifest:

```json
{
  "connector_id": "calendar",
  "connector_type": "native_local",
  "provider_type": "LOCAL",
  "label": "Family Calendar",
  "description": "Household calendar managing events for all family members",
  "version": "1.0.0",
  "provider_id": "native.family.calendar",

  "resource_kinds": ["calendar_event", "calendar"],
  "actor_scope": ["parent", "child_read_own", "system"],

  "constitution": {
    "preconditions": {
      "create_event": ["list_events for target time window before create"],
      "update_event": ["get_event before update"],
      "delete_event": ["get_event before delete"]
    },
    "companion_resource_roles": {
      "participant": "household_member",
      "conflict_subject": "calendar_event"
    },
    "verification": {
      "create_event": "read_after_write via get_event",
      "update_event": "read_after_write via get_event"
    }
  },

  "capabilities": [
    {
      "capability_name": "tool.read.calendar.list_events",
      "operation": "list",
      "effect": "read",
      "resource_kind": "calendar_event",
      "description": "List events in a calendar within a time window",
      "required_inputs": ["calendar_id", "time_min", "time_max"],
      "optional_inputs": ["max_results", "single_events"],
      "output_schema_ref": "calendar_event_list.schema.json",
      "safety_band_min": "GREEN",
      "risk_class": "read_only"
    },
    {
      "capability_name": "tool.read.calendar.get_event",
      "operation": "read",
      "effect": "read",
      "resource_kind": "calendar_event",
      "required_inputs": ["calendar_id", "event_id"],
      "output_schema_ref": "calendar_event.schema.json",
      "safety_band_min": "GREEN",
      "risk_class": "read_only"
    },
    {
      "capability_name": "tool.execute.calendar.create_event",
      "operation": "create",
      "effect": "write",
      "resource_kind": "calendar_event",
      "required_inputs": ["calendar_id", "title", "start", "end"],
      "optional_inputs": ["description", "participants", "location", "all_day"],
      "output_schema_ref": "calendar_event_created.schema.json",
      "safety_band_min": "GREEN",
      "risk_class": "household_write",
      "idempotency": "required",
      "compensation_capability": "tool.execute.calendar.delete_event"
    }
  ],

  "policy_declarations": {
    "write_requires_actor_role": ["parent", "system"],
    "read_allowed_roles": ["parent", "child_read_own"],
    "hil_triggers": ["delete_event if participants > 1"],
    "protected_resources": []
  },

  "registration_type": "executable",
  "admission_verdict": "admitted"
}
```

### Connector Store Location

```text
poc/back_tool_contract/connectors/
  manifests/
    calendar.json
    tasks.json
    reminders.json
    ... (40 manifest files)
  schemas/
    calendar_event.schema.json
    calendar_event_list.schema.json
    ... (output schemas for all capabilities)
  index/
    connector_index.json       by connector_type, provider_type
    capability_index.json      by resource_kind, operation, effect
    resource_kind_index.json   by kind, connected resources, aliases
```

---

## 4. Global Projection Design

### What Is Global Projection

Global projection is the complete catalog of connectors, capabilities, resource kinds, and operation definitions that the system knows about. It is connector-world knowledge, not user-world knowledge.

```text
Global projection answers:
  - What connectors exist in this deployment?
  - What capabilities does each connector expose?
  - What resource kinds does each connector operate on?
  - What is the connector constitution for each operation?
  - Which capabilities are executable vs guide-only?
  - What are the safety band requirements per capability?

Global projection does NOT answer:
  - Does this actor have a calendar connected?
  - Are there events in Riley's calendar today?
  - What is the current state of any resource?
```

Global projection is relatively static. It changes when connectors are added, removed, updated, or when manifests are re-admitted.

### Global Projection Store

```text
Component: MaterializedCapabilityRegistry (CC-4)
Backend: SQLite with FTS5 and indexed columns
Location: poc/back_tool_contract/stores/global_projection.db
Scale target: 100,000 capability contracts (proven by PROD-BACK-100K probe)
```

Schema:

```sql
-- Connector registry
CREATE TABLE connectors (
  connector_id        TEXT PRIMARY KEY,
  label               TEXT NOT NULL,
  connector_type      TEXT NOT NULL,   -- native_local | bridge | ifl_read | ifl_write | system
  provider_type       TEXT NOT NULL,
  version             TEXT NOT NULL,
  admission_verdict   TEXT NOT NULL,   -- admitted | catalog_only | rejected | suspended
  registration_type   TEXT NOT NULL,   -- executable | guide_only
  constitution_json   TEXT,
  policy_json         TEXT,
  resource_kinds_json TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

-- Capability contract registry
CREATE TABLE capabilities (
  capability_name     TEXT PRIMARY KEY,
  connector_id        TEXT NOT NULL REFERENCES connectors(connector_id),
  operation           TEXT NOT NULL,   -- list | read | create | update | delete | compute | fire
  effect              TEXT NOT NULL,   -- read | write | side_effect | system
  resource_kind       TEXT NOT NULL,
  description         TEXT NOT NULL,
  required_inputs_json TEXT NOT NULL,
  optional_inputs_json TEXT,
  output_schema_ref   TEXT,
  safety_band_min     TEXT NOT NULL,
  risk_class          TEXT NOT NULL,
  idempotency         TEXT,            -- required | supported | none
  compensation_capability TEXT,
  record_type         TEXT NOT NULL,   -- executable | guide_only | catalog_ref
  created_at          TEXT NOT NULL
);

-- FTS index for catalog discovery
CREATE VIRTUAL TABLE capabilities_fts USING fts5(
  capability_name,
  description,
  resource_kind,
  operation,
  content='capabilities',
  content_rowid='rowid'
);

-- Resource kind definitions
CREATE TABLE resource_kinds (
  kind                TEXT PRIMARY KEY,
  label               TEXT NOT NULL,
  description         TEXT NOT NULL,
  primary_connector_id TEXT,
  aliases_json        TEXT,
  created_at          TEXT NOT NULL
);

-- Connector constitution store
CREATE TABLE connector_constitutions (
  connector_id        TEXT NOT NULL REFERENCES connectors(connector_id),
  operation           TEXT NOT NULL,
  preconditions_json  TEXT,
  companion_roles_json TEXT,
  verification_json   TEXT,
  PRIMARY KEY (connector_id, operation)
);
```

### Global Projection Query Patterns

```text
1. Find connectors for a resource kind:
   SELECT * FROM connectors
   JOIN resource_kind_assignments ON ...
   WHERE resource_kind = 'calendar_event'
   AND admission_verdict = 'admitted'

2. Find capabilities by operation + effect (execution authority lookup):
   SELECT * FROM capabilities
   WHERE resource_kind = 'calendar_event'
   AND operation = 'create'
   AND effect = 'write'
   AND record_type = 'executable'

3. FTS catalog discovery (research only, not execution authority):
   SELECT * FROM capabilities_fts
   WHERE capabilities_fts MATCH 'dentist appointment OR calendar'
   ORDER BY rank

4. Get connector constitution:
   SELECT * FROM connector_constitutions
   WHERE connector_id = 'calendar'
   AND operation = 'create_event'
```

### Global Projection Admission Flow

```text
ManifestAdmissionService receives raw IFL manifest or native ToolDefinition
  -> validates manifest schema
  -> checks registration_type: executable vs guide_only
  -> checks safety compliance
  -> produces ManifestAdmissionRecord
    admission_verdict: admitted | catalog_only | rejected | suspended
    reason
    guide_ref when catalog_only
  -> writes to connectors, capabilities, resource_kinds tables
  -> writes to FTS index
  -> never writes catalog_only manifests as executable capabilities
```

### Global Projection Proof

```text
M9 probe: manifest_translator correctly classifies executable vs guide_only manifests.
  Assert: guide_only manifest produces record_type=guide_only, no executable capability row.
  Assert: admitted manifest produces record_type=executable and correct indexes.
  Assert: rejected manifest produces ManifestAdmissionRecord.admission_verdict=rejected.

Scale proof: PROD-BACK-100K inserts 100,000 capability rows and verifies indexed lookup
  remains under 5ms p99.
```

---

## 5. Local Projection Design

### What Is Local Projection

Local projection is the current state of user-world resources for this actor and session. It answers actor-specific questions.

```text
Local projection answers:
  - Does this actor have a calendar connected?
  - What is the resource_id for "family calendar"?
  - Who is "Riley" in this household?
  - What aliases resolve to which person?
  - Are there events in the target time window?
  - Is the projection fresh enough to authorize a write?

Local projection does NOT answer:
  - What capabilities exist globally?
  - Which connector handles calendar events in general?
```

Local projection is per-actor and per-session. It is consumed by:

```text
CC-2 ResolveResources: resource identity resolution
CC-1 CandidateUniverse builder: scoping which connectors are active
InvocationPreflight: freshness check before side effects
```

### Local Projection Store

```text
Component: ConnectedResourceRegistry + ResourceProjectionStore
Backend: SQLite with indexed columns
Location: poc/back_tool_contract/stores/local_projection.db
Scope: per actor_id, per space_id
```

Schema:

```sql
-- Connected resources (which connectors are active for this actor)
CREATE TABLE connected_resources (
  resource_id         TEXT PRIMARY KEY,
  actor_id            TEXT NOT NULL,
  space_id            TEXT NOT NULL,
  connector_id        TEXT NOT NULL,
  resource_kind       TEXT NOT NULL,
  label               TEXT NOT NULL,
  aliases_json        TEXT,           -- ["family calendar", "main calendar"]
  status              TEXT NOT NULL,  -- active | suspended | revoked | pending
  actor_permission    TEXT NOT NULL,  -- read_write | read_only | restricted
  last_synced_at      TEXT,
  freshness_state     TEXT NOT NULL,  -- fresh | stale | unknown
  created_at          TEXT NOT NULL
);

-- Household members / people (person-kind resources)
CREATE TABLE household_members (
  person_id           TEXT PRIMARY KEY,
  actor_id            TEXT NOT NULL,
  space_id            TEXT NOT NULL,
  display_name        TEXT NOT NULL,
  aliases_json        TEXT,           -- ["Riley", "Riley K", "rk"]
  role                TEXT NOT NULL,  -- parent | child | guardian | guest
  resource_ids_json   TEXT,           -- linked calendar_id, contact_id, etc
  created_at          TEXT NOT NULL
);

-- Alias index (fast text lookup)
CREATE TABLE alias_index (
  alias_lower         TEXT NOT NULL,
  entity_type         TEXT NOT NULL,  -- resource | person
  entity_id           TEXT NOT NULL,
  actor_id            TEXT NOT NULL,
  space_id            TEXT NOT NULL,
  PRIMARY KEY (alias_lower, actor_id, entity_type)
);

-- Resource projection snapshots (what did the connector last return)
CREATE TABLE resource_projection_snapshots (
  snapshot_id         TEXT PRIMARY KEY,
  resource_id         TEXT NOT NULL,
  connector_id        TEXT NOT NULL,
  resource_kind       TEXT NOT NULL,
  actor_id            TEXT NOT NULL,
  query_window_json   TEXT,           -- time_min, time_max, query params used
  result_summary_json TEXT,           -- items found, counts, key fields only
  raw_ref             TEXT,           -- external ref to full result if needed
  freshness_state     TEXT NOT NULL,
  observed_at         TEXT NOT NULL,
  expires_at          TEXT NOT NULL
);
```

### Local Projection Query Patterns

```text
1. Resolve person reference:
   SELECT person_id, display_name, role, resource_ids_json
   FROM household_members
   WHERE actor_id = :actor_id
   AND JSON_EACH(aliases_json) has value matching alias_lower

   (Or via alias_index:)
   SELECT entity_id FROM alias_index
   WHERE alias_lower = lower('Riley')
   AND entity_type = 'person'
   AND actor_id = :actor_id

2. Find connected calendars for actor:
   SELECT * FROM connected_resources
   WHERE actor_id = :actor_id
   AND resource_kind = 'calendar'
   AND status = 'active'
   AND actor_permission IN ('read_write', 'read_only')

3. Check freshness of a resource:
   SELECT freshness_state, last_synced_at
   FROM connected_resources
   WHERE resource_id = :resource_id

4. Find existing projection snapshot for time window:
   SELECT * FROM resource_projection_snapshots
   WHERE resource_id = :resource_id
   AND connector_id = :connector_id
   AND observed_at > :cutoff
   AND expires_at > NOW()
```

### Local Projection Sources And Update Path

```text
Session start:
  SessionState/grounding envelope seeds initial connected_resources
  Household member records seed alias_index

Connector reads (list_events, get_event, etc):
  After each read invocation, InvocationObservation result feeds a ProjectionDelta
  ProjectionDelta is applied to resource_projection_snapshots
  freshness_state is updated to fresh for the covered time window

Projection delta ingestion:
  M10 (probe_projection_delta.py) proves this path
  ProjectionDelta carries: resource_id, connector_id, window, items, observed_at, expires_at
  Delta is applied as upsert; old non-overlapping windows are not invalidated

Staleness:
  freshness_state = stale when observed_at + ttl < now
  Stale projection blocks non-read side effects unless policy allows queued execution
  Inferred projection (from prior loop iterations) is lower confidence than live-read projection
```

### Local Projection Scope Proof

The resolver must produce a `ScopeProof` with every `CandidateUniverse`:

```json
{
  "scope_proof_id": "sp_001",
  "actor_id": "user_123",
  "space_id": "space_abc",
  "projection_sources": [
    {
      "source": "connected_resources",
      "resource_ids_considered": ["calendar.family.primary"],
      "freshness_state": "fresh",
      "queried_at": "2026-05-31T17:00:00Z"
    },
    {
      "source": "household_members",
      "member_ids_considered": ["person.riley"],
      "freshness_state": "fresh",
      "queried_at": "2026-05-31T17:00:00Z"
    }
  ],
  "omissions": [],
  "exclusions": [],
  "completeness": "complete"
}
```

---

## 6. Component Design — Authority Chain

These are the components that must be built, proven, and model-tested. They are listed in execution order through the authority chain. Each component has a design contract, a proof milestone, and a model-test requirement.

---

### C-01 BackTaskEnvelope

**Whiteboard ref:** CC-0
**Proof milestone:** M1

**What it is:**
The intake wrapper that Back receives from FSM. It carries the TaskDispatch plus correlation, actor/session scope, snapshot refs, and safety context.

**Current reality:**
Back receives a raw dict payload from the FSM mailbox. task_id, trace_id, session_id are injected as loose attributes. There is no BackTaskEnvelope type today.

**Target schema:**

```json
{
  "envelope_id": "env_001",
  "task_id": "task_abc",
  "trace_id": "trace_xyz",
  "session_id": "sess_123",
  "actor_id": "user_456",
  "space_id": "space_789",
  "tier": "tier2",
  "safety_band": "GREEN",
  "task_dispatch": { ... TaskDispatch payload ... },
  "session_state_ref": "ss_snapshot_ref_001",
  "grounding_envelope_id": "grounding_001",
  "temporal_anchor_id": "ta_001",
  "spatial_context_id": "sc_001",
  "submitted_at": "2026-05-31T17:00:00Z",
  "budget": {
    "max_iterations": 10,
    "max_fabric_calls": 5,
    "max_prompt_tokens": 4096
  }
}
```

**Code home:**

```text
k1/concierge/task/back_task_envelope.py   BackTaskEnvelope dataclass + from_fsm_payload()
k1/concierge/actors/back.py               parse_back_task_envelope()
```

**Proof assertions (M1):**

```text
- BackTaskEnvelope deserializes correctly from FSM payload.
- envelope_id is generated if absent.
- trace_id/session_id are present or generated.
- tier is canonical LOW | MEDIUM | HIGH.
- safety_band is GREEN | AMBER | RED.
- missing required fields raise BackTaskEnvelopeError (not silent None).
```

**Negative proof:**

```text
- Missing task_id raises BackTaskEnvelopeError.
- Unknown tier value raises BackTaskEnvelopeError.
- Malformed task_dispatch raises BackTaskEnvelopeError.
```

---

### C-02 RequestFrame

**Whiteboard ref:** Contract A
**Proof milestone:** M1 + M2

**What it is:**
Back builds a RequestFrame from the BackTaskEnvelope. This is Back's structured interpretation of the user intent. It is the input to resolve_situation.

**Current reality:**
No RequestFrame type exists. Back assembles the task JSON into a prompt string.

**Target schema:**

```json
{
  "request_id": "req_001",
  "task_id": "task_abc",
  "trace_id": "trace_xyz",
  "actor_id": "user_456",
  "space_id": "space_789",
  "intents": [
    {
      "intent_id": "int_001",
      "action": "create_calendar_event",
      "domain": "calendar",
      "operation_hint": "create",
      "resource_kind_hint": "calendar_event",
      "subject_hint": "Riley dentist appointment",
      "params": {
        "duration_minutes": 45,
        "person_hint": "Riley",
        "calendar_hint": "family calendar",
        "date_hint": "tomorrow",
        "time_hint": "5pm"
      }
    }
  ],
  "time_window_hint": {
    "raw_phrase": "tomorrow at 5pm",
    "resolved_start": "2026-06-01T17:00:00-07:00",
    "resolved_end": "2026-06-01T17:45:00-07:00",
    "confidence": "high"
  },
  "person_refs": [
    {
      "raw": "Riley",
      "confidence": "high",
      "needs_resolution": true
    }
  ],
  "resource_refs": [
    {
      "raw": "family calendar",
      "resource_kind_hint": "calendar",
      "confidence": "high",
      "needs_resolution": true
    }
  ],
  "safety_context": {
    "safety_band": "GREEN",
    "actor_role": "parent"
  },
  "target_tier": "tier2",
  "resolution_mode": "execution",
  "created_at": "2026-05-31T17:00:00Z"
}
```

**RequestFrame builder:**

```text
RequestFrameBuilder.build(envelope: BackTaskEnvelope) -> RequestFrame
  - parse intents from task_dispatch.intents
  - extract person_refs, resource_refs, time_window_hint from intent params
  - resolve relative time references through TemporalAnchor
  - derive operation_hint from intent action keyword
  - derive resource_kind_hint from domain / intent action
  - attach safety_context from envelope safety_band
  - set resolution_mode = execution (not catalog)
```

**Proof assertions (M1):**

```text
- All 100 scenario phrases produce a valid RequestFrame.
- person_refs are extracted for scenarios with person hints.
- time_window_hint is resolved for concrete time phrases.
- Missing time produces time_window_hint with confidence=low.
- operation_hint correctly maps create/add/update/delete/list/find.
```

---

### C-03 resolve_situation Tool Surface

**Whiteboard ref:** CC-1 / Contract B
**Proof milestone:** M2, M2A (prompt surface), M2B (live LLM)

**What it is:**
The tool Back calls to get resolution authority. It replaces `discover_capabilities` as the authority entry point.

**Current reality:**
No resolve_situation tool exists. discover_capabilities returns top-K records used directly as authority.

**Tool declaration for LLM:**

```json
{
  "name": "resolve_situation",
  "description": "Resolve the current situation and get what I am allowed to do next. I must call this before any side-effecting operation. Returns allowed_next_actions, resource summaries, and connector guidance.",
  "parameters": {
    "type": "object",
    "properties": {
      "request_frame_id": {
        "type": "string",
        "description": "The request frame to resolve"
      },
      "disclosure_phase": {
        "type": "string",
        "enum": ["connector_summary", "tool_name_selection", "schema_binding", "execution"],
        "description": "What level of information I need right now"
      },
      "previous_resolution_id": {
        "type": "string",
        "description": "Prior resolution ID if refreshing or extending"
      }
    },
    "required": ["request_frame_id", "disclosure_phase"]
  }
}
```

**Tool implementation:**

```text
execute_resolve_situation(request_frame_id, disclosure_phase, previous_resolution_id=None, ctx)
  -> Loads RequestFrame from frame store
  -> Builds ResolveSituationRequest
  -> Calls resolver_service.resolve(request)
  -> Receives ResolutionEnvelope
  -> Injects ResolutionEnvelope as PromptPack into Back context
  -> Returns compact tool result to Back model
```

**Compact tool result visible to LLM:**

```json
{
  "resolution_id": "res_001",
  "verdict": "can_execute_with_prerequisite_read",
  "candidate_summary": {
    "calendar": "Family Calendar (fresh, read_write)",
    "persons": ["Riley (child)"]
  },
  "allowed_next_actions": [
    "invoke binding bind_001 (list_events to check conflicts)"
  ],
  "forbidden_next_actions": [
    "invoke create_event until conflict read completes"
  ],
  "guide": "Check for conflicts in target time window before creating event.",
  "missing_fields": [],
  "needs_disambiguation": false
}
```

**What stays hidden from LLM:**

```text
- ScopeProof details
- PolicyBundle raw document
- binding_id internals (LLM gets compact binding name)
- full connector manifest
- resource IDs
- tokens/secrets
```

**Proof assertions (M2):**

```text
- All 100 scenarios produce a ResolutionEnvelope with correct verdict.
- allowed_next_actions are correctly constrained by connector constitution.
- Missing person reference returns needs_disambiguation=true.
- Stale projection returns stale_projection verdict.
- Policy block returns blocked_by_policy verdict.
```

**M2A proof (prompt surface):**

```text
- Compact tool result contains no raw catalog, no full manifest, no tokens.
- PromptPack injection at correct ReAct phase.
- RedactionEvidence.prompt_visible_leak_count = 0.
```

**M2B proof (live LLM):**

```text
- Run with --live against real Gemini Pro, GPT-4o, Claude Sonnet.
- LLM calls resolve_situation before any invoke_capability.
- LLM respects allowed_next_actions and does not call forbidden actions.
- LLM handles disambiguation prompts correctly.
```

---

### C-04 Resolver Internal Pipeline

**Whiteboard ref:** CC-2 (resource resolution), CC-3 (policy), CC-4 (binding)
**Proof milestones:** M3 (resource projection), M4 (policy), M5 (binding)

This is the internal pipeline that runs inside the resolver. The LLM does not see this. Back calls resolve_situation; resolver runs this internally.

#### C-04a Resource Resolution (CC-2)

**What it does:**
Takes person_refs, resource_refs, time_window_hint from RequestFrame and resolves them to concrete resource IDs from local projection.

**Internal process:**

```text
ResolveResourcesService.resolve(request: ResolveResourcesRequest)

Step 1: Alias resolution
  For each person_ref:
    query alias_index WHERE alias_lower = lower(ref.raw) AND actor_id = actor_id
    if 0 results -> unresolved_person
    if 1 result  -> resolved to person_id
    if 2+ results -> ambiguous_person

  For each resource_ref:
    query alias_index WHERE alias_lower = lower(ref.raw) AND actor_id = actor_id
    if 0 results -> try connected_resources WHERE label contains ref.raw
    if 1 result  -> resolved to resource_id
    if 2+ results -> ambiguous_resource

Step 2: Active resource filter
  For each resolved resource_id:
    check connected_resources.status = 'active'
    check connected_resources.actor_permission allows the operation
    check freshness_state

Step 3: Connector scope
  For each resolved resource:
    look up connector_id from connected_resources
    verify connector.admission_verdict = 'admitted'
    verify connector.registration_type = 'executable' for write operations

Step 4: ResourceUniverse output
  resource_candidates: resolved resources with connector, freshness, permission
  person_candidates: resolved people with role, linked resources
  unresolved: any refs not resolved with reason
  omissions: connectors considered but excluded with reason
  completeness: complete | partial | unknown
```

**Search style:**

```text
Exact alias match (primary):  SELECT from alias_index WHERE alias_lower = lower(input)
Fuzzy text fallback:          Only when exact alias returns 0 results; LIKE '%riley%' on labels
FTS5 search:                  Only for catalog discovery, never for final resource authority
Vector/BM25:                  Never for resource identity authorization; only for catalog browsing
```

**Proof assertions (M3):**

```text
- "Riley" resolves to correct person_id.
- "family calendar" resolves to correct resource_id.
- Ambiguous "Riley" returns ambiguous_person.
- Missing person returns unresolved.
- Connected resource with stale freshness is flagged as stale.
- Resource with revoked status is excluded with reason.
- ScopeProof lists every resource_id considered.
```

#### C-04b Policy Selection (CC-3)

**What it does:**
Given resolved resources and requested operation, selects the applicable PolicyBundle.

**Internal process:**

```text
PolicySelectorService.select(request: PolicySelectionRequest)

Inputs:
  resource_ids, connector_ids, operations, actor_role, safety_band

Policy sources checked in order:
  1. connector-level policy_declarations in connector manifest
  2. resource-kind-level policy rules
  3. global household safety band policy
  4. actor role policy

Outputs:
  PolicyBundle:
    policy_id
    roles_allowed: {operation: [role]}
    gates: list of policy gate declarations
      - precondition gates (list_before_create)
      - HIL trigger gates (delete when participants > 1)
      - safety band gate (min required band per operation)
    protected_read_policy: for classified resources
    hil_triggers: structured trigger declarations
    guide_refs: guide cards relevant to this operation
    verifier_requirements: which operations require read_after_write
    policy_verdict: allow | deny | allow_with_gate | needs_hil
```

**Policy is not executable:**

```text
PolicyBundle does not choose a capability_name.
PolicyBundle does not say which provider to use.
PolicyBundle says what is permitted, required, and what triggers HIL.
Capability binding happens in CC-4, after policy.
```

**Proof assertions (M4):**

```text
- Calendar write operation for parent role returns policy_verdict=allow_with_gate.
- Calendar write operation for child role returns policy_verdict=deny.
- delete_event with participants > 1 returns hil_triggers=[delete_with_participants].
- Safety band mismatch returns policy_verdict=deny with SafetyMappingEvidence.
- Policy bundle includes verifier_requirements=read_after_write for create_event.
```

#### C-04c Capability Binding (CC-4)

**What it does:**
Given resolved resources, allowed roles, and selected policy, binds exact capability contracts.

**Internal process:**

```text
CapabilityBinderService.bind(request: BindingRequest)

Inputs:
  resource_candidates, policy_bundle, operation_hints, actor_scope, disclosure_phase

For each intended operation:
  1. Exact registry lookup
     SELECT * FROM capabilities
     WHERE resource_kind = :resource_kind
     AND operation = :operation
     AND effect = :effect
     AND connector_id = :connector_id
     AND record_type = 'executable'
     AND safety_band_min <= :safety_band

  2. Policy gate check
     verify actor_role satisfies policy_bundle.roles_allowed[operation]

  3. Idempotency check
     if operation is write: verify idempotency is required or supported

  4. Build CapabilityBinding
     binding_id = deterministic hash of (connector_id, capability_name, resource_id, actor_id, session_id)
     role = primary_write | prerequisite_read | verification_read | companion_read
     freshness_state = from connected resource
     verifier_ref = from connector constitution

  5. Staged disclosure
     Phase 1 (names only):  tool_name_cards with names, descriptions, no schemas
     Phase 2 (selected):    model commits which tools it will use
     Phase 3 (schemas):     full input schemas only for committed bindings

Outputs:
  BindingBundle:
    binding_bundle_id
    bindings: [CapabilityBinding]
    unbound_roles: operations with no matching capability and reason
    tool_name_cards: names only at Phase 1
    selected_schema_cards: full schemas only after Phase 2 commit
    guide_refs, verifier_links
```

**Proof assertions (M5):**

```text
- create_event resolves to binding_id with capability_name=tool.execute.calendar.create_event.
- list_events resolves to a prerequisite_read binding.
- guide_only manifest produces unbound_role, not a binding.
- Phase 1 response contains names only, no schemas.
- Phase 3 response contains schemas only for committed bindings.
- Stale connected resource produces freshness_state=stale on the binding.
```

---

### C-05 CandidateUniverse

**Whiteboard ref:** Contract F
**Proof milestone:** M3 + M5 (built from CC-2 + CC-4 outputs)

**What it is:**
The complete, scoped, ranked-but-authority-checked universe of what Back can do for this request. It is the single source of truth for allowed_next_actions.

**Schema:**

```json
{
  "universe_id": "univ_001",
  "resolution_id": "res_001",
  "scope_proof": { ... ScopeProof ... },
  "connector_candidates": [
    {
      "connector_id": "calendar",
      "label": "Family Calendar",
      "constitution_summary": "list_events before create, read_after_write verify",
      "in_scope": true,
      "freshness": "fresh"
    }
  ],
  "resource_candidates": [
    {
      "resource_id": "calendar.family.primary",
      "label": "Family Calendar",
      "resource_kind": "calendar_event",
      "connector_id": "calendar",
      "actor_permission": "read_write",
      "freshness_state": "fresh"
    }
  ],
  "person_candidates": [
    {
      "person_id": "person.riley",
      "label": "Riley",
      "role": "child",
      "resolved": true
    }
  ],
  "capability_bindings": [
    {
      "binding_id": "bind_001",
      "role": "prerequisite_read",
      "capability_name": "tool.read.calendar.list_events",
      "resource_id": "calendar.family.primary"
    },
    {
      "binding_id": "bind_002",
      "role": "primary_write",
      "capability_name": "tool.execute.calendar.create_event",
      "resource_id": "calendar.family.primary"
    }
  ],
  "companion_resource_roles": {},
  "cross_resource_read_requirements": [],
  "allowed_next_actions": ["invoke bind_001"],
  "forbidden_next_actions": ["invoke bind_002 before bind_001 completes"],
  "omissions": [],
  "exclusions": [],
  "completeness": "complete",
  "freshness": "fresh",
  "policy_verdict": "allow_with_gate",
  "expires_at": "2026-05-31T17:05:00Z"
}
```

**Invariant I5 — Candidate completeness before ranking:**

```text
All connectors that could plausibly handle the operation must be considered and either included
or explicitly excluded with a reason. Silent omission is forbidden.
If completeness is partial or unknown, side effects and protected reads are blocked by default.
```

---

### C-06 ResolutionEnvelope

**Whiteboard ref:** Contract E
**Proof milestone:** M2 + M12A

**What it is:**
The complete output of resolve_situation. It carries CandidateUniverse, PromptPack, and the authority verdict.

**Schema:**

```json
{
  "resolution_id": "res_001",
  "request_id": "req_001",
  "request_frame": { ... RequestFrame echo ... },
  "candidate_universe": { ... CandidateUniverse ... },
  "prompt_pack": { ... PromptPack ... },
  "policy_bundle_ref": "pol_001",
  "binding_bundle_ref": "bnd_001",
  "completeness": "complete",
  "freshness": "fresh",
  "verdict": "can_execute_with_prerequisite_read",
  "allowed_next_actions": ["invoke bind_001"],
  "diagnostics": [],
  "created_at": "2026-05-31T17:00:00Z",
  "expires_at": "2026-05-31T17:05:00Z"
}
```

**Verdict taxonomy:**

```text
can_execute              -> proceed, all clear
can_execute_with_gate    -> proceed after gate actions (prerequisite reads)
needs_disambiguation     -> HIL required to resolve ambiguous reference
missing_required_params  -> incomplete RequestFrame, needs Back to ask or HIL
missing_capability       -> no admitted capability for this operation
blocked_by_policy        -> policy hard deny
stale_projection         -> local projection too stale for side effects
incomplete_world_projection -> cannot confirm resource scope
promote_to_tier3         -> task is cross-resource/companion-bearing, escalate
cannot_execute           -> budget or safety block
```

---

### C-07 PromptPack

**Whiteboard ref:** Contract G / CC-10
**Proof milestone:** M11

**What it is:**
The compact, redacted, phase-specific context injected into Back's model context. It is the only legitimate route for authority material to reach the LLM.

**Phase-specific content:**

```text
loop_start:
  - Back executor role declaration
  - Task envelope summary (task goal, tier, budget)
  - SessionState task snapshot
  - Grounding block

after_request_frame:
  - Compact RequestFrame summary
  - Known missing fields
  - Allowed resolution modes

after_resolution (connector_summary phase):
  - Constitution cards: connector preconditions, companion roles, verification requirement
  - Tool name cards: capability names + one-line descriptions ONLY (no schemas)
  - Policy cards: what is required, what triggers HIL, what is denied
  - Guide cards: relevant procedural guides
  - CandidateUniverse summary: person/resource labels, freshness, allowed_next_actions
  - Omission summary

after_tool_selection (schema_binding phase):
  - Selected schema cards: FULL input schemas for committed tools only

after_invocation:
  - InvocationObservation summary (status, result_summary, errors)
  - VerificationObservation when available
  - RecoveryDirective when applicable
  - Updated allowed_next_actions

after_hil_response:
  - HILResponse summary
  - Changed constraints
  - Updated resolution_id reference

final_iteration:
  - Termination reminder
  - submit_result schema
  - Unresolved obligations summary
```

**Redaction invariants:**

```text
Never in any PromptPack:
  - Raw connector manifests
  - Full PolicyBundle document
  - Tokens, secrets, credentials, oauth tokens
  - Raw provider API payloads
  - Full schemas for unbound/uncommitted tools
  - ScopeProof details
  - binding_id raw internals (use compact binding label)
  - resource_id raw values (use labels)
```

**RedactionEvidence (must accompany every pack):**

```json
{
  "redaction_id": "red_001",
  "prompt_hash": "sha256:...",
  "fields_redacted": ["policy_bundle.raw_doc", "scope_proof.projection_sources"],
  "fields_verified_absent": ["token", "secret", "credential", "oauth"],
  "prompt_visible_leak_count": 0,
  "verdict": "pass"
}
```

**Proof assertions (M11):**

```text
- PromptPack injected at correct phase for all 100 scenarios.
- RedactionEvidence.prompt_visible_leak_count = 0 for all scenarios.
- Tool name cards in after_resolution contain names only, no full schemas.
- Full schemas appear only after schema_binding phase and only for committed tools.
- Stale card does not appear in allowed_next_actions.
- Raw catalog injection produces M11 FAIL.
- Secret field in pack produces M11 FAIL.
```

---

### C-08 Invocation Request And Preflight

**Whiteboard ref:** Contract H / CC-5
**Proof milestone:** M6

**What it is:**
The validated, authority-checked invocation request sent to Fabric. Back assembles params from PromptPack guidance; Fabric preflights everything before provider dispatch.

**Schema:**

```json
{
  "invocation_id": "inv_001",
  "resolution_id": "res_001",
  "binding_id": "bind_002",
  "capability_name": "tool.execute.calendar.create_event",
  "params": {
    "calendar_id": "calendar.family.primary",
    "title": "Riley dentist appointment",
    "start": "2026-06-01T17:00:00-07:00",
    "end": "2026-06-01T17:45:00-07:00",
    "participants": ["person.riley"]
  },
  "idempotency_key": "task_abc:create_event:calendar.family.primary:20260601T170000",
  "actor_ref": "user_456",
  "safety_context": { "safety_band": "GREEN", "actor_role": "parent" },
  "policy_gate_refs": ["pol_001"],
  "expected_effect": "write",
  "verifier_requested": true
}
```

**Preflight checks in order:**

```text
1. binding_id exists in binding store and is not stale.
   Failure: InvocationPreflightVerdict stale_resolution -> RecoveryDirective refresh_projection

2. params satisfy binding's input_schema_ref (JSON Schema validation).
   Failure: capability_params_incomplete -> retry_with_params + suggested_params_patch

3. idempotency_key present for side-effecting operations.
   Failure: missing_idempotency_key -> block (this is a code bug, not user error)

4. idempotency store check: has this key succeeded before?
   If yes: return prior success result (no-op)
   If in-flight: return retryable conflict

5. Policy gate refs still valid (re-check at invocation time).
   Failure: policy_gate_expired or policy_deny -> block_and_submit

6. Safety context maps to capability safety_band_min.
   Failure: SafetyMappingEvidence -> typed denied with hard_block_reason

7. Resource projection freshness re-check.
   Failure: stale_projection -> block for writes, allow for reads

8. Param normalization:
   duration_minutes -> end (if provider needs end and only duration given)
   person_id -> provider-specific participant format
   resource_id -> connector-specific calendar_id format
```

**Proof assertions (M6):**

```text
- Valid InvocationRequest produces invocation and InvocationObservation.
- Missing end + duration_minutes produces capability_params_incomplete with recovery patch.
- Stale binding_id produces stale_resolution with refresh_projection recovery.
- Duplicate idempotency_key after success is a no-op returning prior result.
- SafetyMappingEvidence produced when safety band does not meet capability minimum.
- All 40 connector schemas validated in preflight.
```

---

### C-09 InvocationObservation

**Whiteboard ref:** Contract H
**Proof milestone:** M6 + M7 + M8

**What it is:**
The normalized result that Back sees after every invocation. Provider-specific formats are translated here; Back never sees raw provider payloads.

**Schema:**

```json
{
  "invocation_id": "inv_001",
  "binding_id": "bind_002",
  "status": "success",
  "provider_status": "200",
  "result_summary": "Calendar event created: Riley dentist appointment 2026-06-01 5pm",
  "artifacts": {
    "event_id": "evt_789"
  },
  "structured_result": {
    "event_id": "evt_789",
    "title": "Riley dentist appointment",
    "start": "2026-06-01T17:00:00-07:00",
    "end": "2026-06-01T17:45:00-07:00"
  },
  "errors": null,
  "recovery_directive": null,
  "verifier_obligation": {
    "method": "read_after_write",
    "readback_capability_ref": "tool.read.calendar.get_event",
    "readback_params": {
      "calendar_id": "calendar.family.primary",
      "event_id": "evt_789"
    }
  },
  "allowed_next_actions": ["invoke verifier for evt_789"],
  "audit_fields": {
    "trace_id": "trace_xyz",
    "invocation_id": "inv_001",
    "binding_id": "bind_002",
    "actor_id": "user_456"
  },
  "latency_ms": 145
}
```

**What Back sees vs what stays hidden:**

```text
Back sees:
  status, result_summary, artifacts, structured_result (safe subset)
  errors (typed, user-visible summary only)
  recovery_directive (action and params)
  verifier_obligation (what to verify next)
  allowed_next_actions

Back never sees:
  raw provider HTTP response
  provider-internal IDs not needed for verification
  auth tokens, credentials
  full stack traces
  audit_fields (those go to audit store, not LLM context)
```

**Proof assertions (M6 native, M7 bridge, M8 IFL):**

```text
- Native provider success produces structured_result with expected fields.
- Bridge dispatch produces ConnectorDispatchObservation, not raw HTTP body.
- IFL adapter success produces IflResultEnvelope fields, no raw external payload.
- Provider failure produces status=failed with error.code, error.user_visible_summary.
- verifier_obligation is present when connector constitution requires verification.
```

---

### C-10 VerificationPlan And VerificationObservation

**Whiteboard ref:** Contract M
**Proof milestone:** M12A (within end-to-end execution)

**What it is:**
The plan for how to verify a side effect completed correctly, and the resulting observation. Provider success is not verified completion.

**VerificationPlan schema:**

```json
{
  "verification_plan_id": "vp_001",
  "resolution_id": "res_001",
  "binding_id": "bind_002",
  "invocation_id": "inv_001",
  "verifier_ref": "verify_calendar_event_readback",
  "verifier_method": "read_after_write",
  "expected_effect": "calendar event exists with title, start, end matching request",
  "expected_resource_state": {
    "event_id": "evt_789",
    "title": "Riley dentist appointment",
    "start": "2026-06-01T17:00:00-07:00",
    "end": "2026-06-01T17:45:00-07:00"
  },
  "readback_capability_ref": "tool.read.calendar.get_event",
  "readback_params": {
    "calendar_id": "calendar.family.primary",
    "event_id": "evt_789"
  },
  "max_staleness_ms": 5000,
  "required_for_submit_status": "completed"
}
```

**VerificationObservation schema:**

```json
{
  "verification_id": "ver_001",
  "verification_plan_id": "vp_001",
  "status": "verified",
  "observed_effect": "calendar event exists with expected title and time",
  "observed_resource_state_ref": "rs_snap_001",
  "mismatch_summary": null,
  "stale_read_summary": null,
  "degraded_reason": null,
  "policy_ref": "pol_001",
  "recovery_directive": null,
  "proof_refs": ["inv_001", "rs_snap_001"]
}
```

**Verification method taxonomy:**

```text
read_after_write       : read the resource and compare to expected_resource_state
output_schema          : validate structured_result against output schema contract
state_compare          : compare before/after snapshots
audit_receipt          : provider returns a receipt that constitutes proof
external_receipt       : external system confirms the effect
policy_attestation     : policy gate confirms the effect is consistent
none_available         : verification is not possible; degraded_completion_policy applies
```

**Invariant I21 — No silent degraded completion:**

```text
If verification is unavailable (none_available), submit_result(completed) requires:
  - explicit degraded_completion_policy in the VerificationPlan
  - VerificationObservation.degraded_reason is set
  - audit record notes the degraded completion
Silent degraded completion is forbidden.
```

**Proof assertions (M12A):**

```text
- create_event produces VerificationPlan with method=read_after_write.
- Readback confirms event exists: VerificationObservation.status=verified.
- Readback finds no event: VerificationObservation.status=failed, submit_result blocked.
- Stale readback: VerificationObservation.status=inconclusive, submit_result blocked.
- none_available without degraded_completion_policy blocks submit_result(completed).
```

---

### C-11 ErrorObservation And RecoveryDirective

**Whiteboard ref:** Contract K
**Proof milestone:** M6 + M12

**What it is:**
Every typed failure produces an ErrorObservation with a RecoveryDirective. Back must follow the directive; it cannot invent its own recovery.

**ErrorObservation schema:**

```json
{
  "error_id": "err_001",
  "source_component": "invocation_preflight",
  "code": "capability_params_incomplete",
  "severity": "recoverable",
  "retryability": "retry_with_patch",
  "user_visible_summary": "I need a start time for the event",
  "developer_code": "missing_required_input: end",
  "context": {
    "capability_name": "tool.execute.calendar.create_event",
    "binding_id": "bind_002",
    "missing_fields": ["end"]
  }
}
```

**RecoveryDirective schema:**

```json
{
  "recovery_id": "rec_001",
  "error_id": "err_001",
  "action": "retry_with_params",
  "suggested_params_patch": {
    "end": "2026-06-01T17:45:00-07:00"
  },
  "required_fields": ["end"],
  "candidate_refs": [],
  "hil_options": null,
  "block_reason": null
}
```

**Recovery action taxonomy:**

```text
ask_hil                  : send HILRequest; do not retry without human input
retry_with_params        : retry with suggested_params_patch applied
refresh_projection       : re-run resolve_situation with refreshed local projection
run_prerequisite_read    : run the prerequisite read first before retrying
choose_from_candidates   : ambiguous; LLM must choose from candidate list
block_and_submit         : unrecoverable; submit_result with cannot_execute or partial
cannot_execute           : hard block; submit_result with failed
```

---

### C-12 HIL Request And Resume

**Whiteboard ref:** Contract I
**Proof milestone:** M12A (HIL gate in duplicate-path scenario)

**What it is:**
When policy, ambiguity, or incomplete params require human input, Back emits a structured HILRequest. Resume carries HILResponse back into the loop.

**HILRequest schema:**

```json
{
  "hil_request_id": "hil_001",
  "task_id": "task_abc",
  "resolution_id": "res_001",
  "hil_type": "disambiguation",
  "prompt": "Which Riley did you mean?",
  "options": [
    {"option_id": "opt_001", "label": "Riley K (child)", "entity_id": "person.riley_k"},
    {"option_id": "opt_002", "label": "Riley T (guest)", "entity_id": "person.riley_t"}
  ],
  "required": true,
  "context_summary": "Trying to add a dentist appointment for Riley",
  "expires_at": "2026-05-31T17:30:00Z"
}
```

**HIL types:**

```text
disambiguation     : ambiguous reference needs user selection
missing_input      : required param not derivable; need user input
confirmation       : policy triggers confirmation before write (delete with participants)
risk_acknowledgement: elevated risk operation needs explicit user acknowledgement
```

---

### C-13 SubmitResult Authority Boundary

**Whiteboard ref:** Contract J
**Proof milestone:** M12A

**What it is:**
Back's final claim about what happened. It is gated: `completed` requires VerificationObservation. The SubmitResult authority boundary is the last component in the loop.

**Schema:**

```json
{
  "result_id": "res_final_001",
  "task_id": "task_abc",
  "resolution_id": "res_001",
  "invocation_id": "inv_001",
  "verification_id": "ver_001",
  "result_type": "completed",
  "summary": "Added Riley's dentist appointment to Family Calendar for June 1 at 5:00pm.",
  "artifacts": {
    "event_id": "evt_789",
    "calendar_id": "calendar.family.primary"
  },
  "evidence": {
    "resolution_id": "res_001",
    "binding_id": "bind_002",
    "invocation_id": "inv_001",
    "verification_id": "ver_001",
    "policy_bundle_ref": "pol_001"
  },
  "unresolved_obligations": [],
  "submitted_at": "2026-05-31T17:00:05Z"
}
```

**result_type taxonomy:**

```text
completed          : side effect verified; VerificationObservation.status=verified required
partial            : some intents completed, some failed; evidence for each
needs_hil          : loop suspended; HILRequest in flight
cannot_execute     : hard block; no side effect occurred
failed             : attempt made and failed; evidence of what was tried
blocked            : policy/safety block; no invocation attempted
```

**Authority gate rule:**

```text
submit_result(completed) is NOT legal when:
  - VerificationObservation is absent for a required-verification operation
  - VerificationObservation.status is failed, inconclusive, or unavailable without degraded_completion_policy
  - InvocationObservation.status is not success or partial
  - Any required allowed_next_action was not taken

ToolDispatcher must enforce this, not just prompt-guide it.
```

---

## 7. LLM Model Matrix

### Purpose

Every model-visible component seam must be tested against multiple LLM backends. The goal is not to find the best model but to prove that the execution contract works with different models and that no component relies on model-specific behavior.

### Model Classes To Test

```text
Large context, high reasoning:
  Gemini 2.5 Pro
  GPT-4o
  Claude Sonnet 4.5 / 4.6

Mid-tier, fast:
  Gemini 2.0 Flash
  GPT-4o-mini
  Claude Haiku

Small/local (future):
  Gemini nano (device)
  Small local model via Ollama
```

### What To Test Per Model

For each model, run all 100 scenarios through the Back ReAct loop and assert:

```text
1. Tool call behavior:
   - LLM calls resolve_situation before any side-effecting invoke_capability.
   - LLM respects allowed_next_actions.
   - LLM does not call forbidden actions.
   - LLM calls submit_result when loop is complete.

2. Disambiguation handling:
   - LLM emits HILRequest when needs_disambiguation=true.
   - LLM does not guess an ambiguous reference.

3. Prerequisite read compliance:
   - LLM calls list_events before create_event in calendar scenarios.
   - LLM does not skip prerequisite reads when they are required.

4. Failure path behavior:
   - LLM follows RecoveryDirective when present.
   - LLM escalates to HIL when recovery_action=ask_hil.
   - LLM calls submit_result(cannot_execute) on hard blocks.

5. Hallucination resistance:
   - LLM does not invent resource IDs.
   - LLM does not claim a side effect completed before InvocationObservation.
   - LLM does not call a capability not in allowed_next_actions.
```

### Model Matrix Proof Record

```json
{
  "matrix_id": "mm_001",
  "model": "gemini-2.5-pro",
  "scenario_ids_run": ["S001", "S002", "..."],
  "scenarios_passed": 96,
  "scenarios_failed": 4,
  "failure_summary": [
    {"scenario_id": "S047", "failure": "skipped prerequisite read on simple create"},
    ...
  ],
  "tool_call_compliance_rate": 0.97,
  "disambiguation_compliance_rate": 1.0,
  "hallucination_rate": 0.01,
  "verdict": "pass_with_minor_failures",
  "run_at": "2026-06-01T00:00:00Z"
}
```

### Minimum Pass Criteria For Production Migration

```text
All components must pass with at least two models in class: large and mid-tier.
No model may have hallucination_rate > 0.05 for side-effecting scenarios.
No model may skip prerequisite reads more than 2% of the time.
Any model with compliance failures triggers a PromptPack review before cutover.
```

---

## 8. Proof Harness Design

### Proof Record Structure

Every milestone produces proof records. Each component test emits a structured record.

```json
{
  "proof_id": "proof_001",
  "milestone_id": "M6",
  "scenario_id": "S041",
  "component": "invocation_preflight",
  "seam": "binding_id_preflight",
  "producer": "invocation_runtime",
  "consumer": "back_react_loop",
  "trace_id": "trace_xyz",
  "request_id": "req_001",
  "input_ref": "scenarios/S041.json",
  "output_ref": "tmp/back_tool_contract/M6/invocation_S041.json",
  "feature_flags": ["CC5_INVOCATION_OBSERVATION"],
  "assertions": [
    {"assertion": "binding_id present in invocation request", "result": "pass"},
    {"assertion": "params validated against schema", "result": "pass"},
    {"assertion": "idempotency_key present", "result": "pass"},
    {"assertion": "InvocationObservation.status = success", "result": "pass"}
  ],
  "redaction_summary": {
    "prompt_visible_leak_count": 0,
    "verdict": "pass"
  },
  "rejected_fields": [],
  "all_pass": true,
  "llm_mock_used": false,
  "run_at": "2026-06-01T00:00:00Z"
}
```

**Rejection rules (proof record is invalid if):**

```text
- llm_mock_used = true for any M2B or M11 or M12 proof.
- trace_id is empty or missing.
- raw_catalog appears in any prompt_capture_ref.
- any secret-like field (token, credential, oauth) in prompt capture.
- assertions array is empty.
```

### Milestone Summary

```text
M0   proof_harness          Proof record infrastructure: write, validate, redact, reject
M1   back_task_envelope     BackTaskEnvelope + RequestFrame deserialization
M2   resolve_situation      ResolutionEnvelope for all 100 scenarios
M2A  resolver_prompt        Prompt surface: no catalog/secret leaks
M2B  resolver_live_llm      Live LLM calls resolve_situation, respects allowed_next_actions
M3   resource_projection    Person/resource/alias resolution from local projection
M4   policy_selector        PolicyBundle for all connector/operation/role combinations
M5   binder                 BindingBundle with staged disclosure for all 40 connectors
M6   invoke_by_binding      InvocationRequest + preflight + InvocationObservation, all scenarios
M7   bridge_dispatch        Bridge/connector gateway invocation path
M8   ifl_adapter            IFL adapter command/result path
M9   manifest_admission     Global projection admission: executable vs guide_only classification
M10  projection_delta       Local projection delta ingestion after read observations
M11  prompt_injection       PromptPack injection at correct phases, RedactionEvidence all pass
M12A resolution_executor    End-to-end Tier 2 with verification, including duplicate-HIL gate
M12  e2e_scenarios          All 100 scenarios end-to-end with real LLM and real providers
```

---

## 9. Production Migration Gate

### Gate Conditions

A component seam moves to production only when all of the following are true:

```text
1. All relevant scenarios pass with all_pass=true in proof records.
2. All negative proof cases produce typed errors, not silent failures.
3. At least 2 LLM backends pass compliance in model matrix.
4. ShadowComparisonRecord for the seam exists and recommends cutover.
5. Feature flag exists and is defaulted OFF.
6. Legacy path still runs when flag is OFF.
7. Rollback target is named.
8. RedactionEvidence.prompt_visible_leak_count = 0.
9. No llm_mock_used = true in any proof record for this seam.
```

### Migration Order

```text
Phase 1 — Authority infrastructure (no LLM-visible change yet):
  BackTaskEnvelope (C-01)
  RequestFrame seed (C-02)
  Global projection store (C-04 CC-4 registry)
  Local projection store (C-04 CC-2 resource resolution)
  ManifestAdmission (M9)

Phase 2 — Resolver as shadow (LLM still uses discover/invoke):
  resolve_situation tool (C-03) behind CC1_RESOLVER_TOOL flag
  ResolutionEnvelope + CandidateUniverse (C-05, C-06)
  PromptPack injection (C-07) behind CC10_PROMPT_INJECTION flag
  Shadow comparison: new resolver runs in parallel with discover_capabilities; results logged but not used for authority

Phase 3 — Resolver as authority for reads:
  allowed_next_actions enforced at dispatch gate for read operations
  InvocationObservation (C-09) normalizer live
  Projection delta ingestion (M10) live

Phase 4 — Resolver as authority for writes:
  BindingBundle authority (C-04c) live behind CC4_BINDING_BUNDLE flag
  InvocationPreflight (C-08) enforced
  VerificationPlan runner (C-10) live behind verification flag
  submit_result authority gate (C-13) enforced
  capability_name fallback retired on proven seams only

Phase 5 — Full cutover and legacy path retirement:
  discover_capabilities demoted to catalog-only mode
  invoke_capability by name remains as fallback only for proven native tool names
  All 100 scenarios running in production via new path
```

---

## 10. Open Design Questions

These must be resolved during POC, before production migration.

```text
OD-01  Exact RequestFrame JSON schema version and migration strategy when it evolves.
OD-02  Which store owns concrete resource projection versions — local_projection.db, SessionState, or both?
OD-03  How long native capability_name values remain valid fallbacks after binding_id path is proven.
OD-04  Exact Back tool set for V1: resolve_situation only, or resolve_situation + inspect_binding?
OD-05  Exact compatibility mapping from legacy native names to connector-aware names.
OD-06  SafetyContext axes: exact mapping from GREEN/AMBER/RED to kernel axes for all 40 connectors.
OD-07  VerificationPlan methods for IFL/bridge connectors: none_available is expected; what is the degraded policy?
OD-08  TraceContext propagation and AuthorityDecisionRecord storage — one store or per-session?
OD-09  How POC SQLite stores are promoted to production storage — SQLite in production, or swap to Postgres/Spanner?
OD-10  ExecutionBudget defaults for prompt cards, context fanout, and max iterations per tier.
OD-11  PromptCaptureRecord retention policy — how long, where, who can read?
OD-12  companion_resource_roles in domain ontology: family calendar + person participant; exact cross-resource resolution for Tier 3.
OD-13  BridgeRuntime slot wiring for ConnectorGateway in production kernel bootstrap.
OD-14  ManifestAdmission trust tiers and mid-session revocation behavior for IFL connectors.
```

---

## 11. File And Directory Layout

### POC Source Layout

```text
poc/back_tool_contract/
  proof.py                        ProofRecordWriter, proof_record_template, redaction helpers
  back_task_envelope.py           BackTaskEnvelope, BackTaskEnvelopeError
  request_frame_builder.py        RequestFrameBuilder
  resolve_situation.py            ResolveSituationService, ResolutionEnvelope
  resource_projection.py          ResolveResourcesService, ResourceUniverse, ScopeProof
  resource_registry.py            ConnectedResourceRegistry (SQLite)
  capability_registry.py          MaterializedCapabilityRegistry (SQLite)
  capability_binder.py            CapabilityBinderService, BindingBundle
  policy_selector.py              PolicySelectorService, PolicyBundle
  invocation_runtime.py           InvocationRuntime, InvocationPreflight, InvocationObservation
  verification_runner.py          VerificationPlanRunner, VerificationObservation
  manifest_registration.py        ManifestAdmissionService, ManifestAdmissionRecord
  projection_delta.py             ProjectionDeltaIngester
  prompt_injection.py             PromptPackBuilder, PromptInjectionEnvelope, RedactionEvidence
  back_react_loop_poc.py          Full POC Back ReAct loop wiring all above components
  connector_dispatch.py           Bridge/ConnectorGateway POC path
  ifl_adapter_runtime.py          IFL adapter command/result path
  resolution_executor.py          End-to-end resolver + binding + invocation + verification
  e2e_scenario_gate.py            End-to-end scenario runner for all 100 scenarios
  live_provider.py                Live LLM + live native provider path

  stores/
    global_projection.db          MaterializedCapabilityRegistry store
    local_projection.db           ConnectedResourceRegistry + ResourceProjectionStore
    idempotency.db                Idempotency key store

  scenarios/
    scenario_corpus.json
    scenario_schema.json
    scenario_index.json

  connectors/
    manifests/                    40 connector manifest JSON files
    schemas/                      Capability output schemas
    index/

  schemas/
    request_frame.schema.json
    resolution_envelope.schema.json
    candidate_universe.schema.json
    prompt_pack.schema.json
    invocation_request.schema.json
    invocation_observation.schema.json
    verification_plan.schema.json
    verification_observation.schema.json
    error_observation.schema.json
    recovery_directive.schema.json
    submit_result.schema.json
    hil_request.schema.json
    hil_response.schema.json
    back_task_envelope.schema.json
```

### Probe Script Layout

```text
scripts/
  probe_back_contract_proof_harness.py     M0
  probe_back_task_envelope.py              M1
  probe_resolve_situation.py               M2
  probe_back_resolver_prompt_surface.py    M2A
  probe_back_resolver_live_llm.py          M2B  requires --live
  probe_resource_projection.py             M3
  probe_policy_selector.py                 M4
  probe_binder.py                          M5
  probe_invoke_by_binding.py               M6
  probe_bridge_dispatch.py                 M7
  probe_ifl_adapter.py                     M8
  probe_manifest_translator.py             M9
  probe_projection_delta.py                M10
  probe_prompt_injection.py                M11  requires --production-provider for M11 live
  probe_resolution_executor.py             M12A
  probe_e2e_scenarios.py                   M12  requires --production-provider
  probe_production_back_runtime.py         PROD-BACK-100K
  probe_back_profiles.py                   live kernel profiles
  _aggregate_probe_gaps.py                 gap audit across all milestones
  _probe_common.py                         shared ProbeReport, fixtures, utilities
```

### Proof Artifact Layout

```text
tmp/back_tool_contract/
  M0/     proof_harness/
  M1/     back_task_envelope/
  M2/     resolve_situation/
  M2A/    resolver_prompt_surface/
  M2B/    resolver_live_llm/
  M3/     resource_projection/
  M4/     policy_selector/
  M5/     binder/
  M6/     invoke_by_binding/
  M7/     bridge_dispatch/
  M8/     ifl_adapter/
  M9/     manifest_admission/
  M10/    projection_delta/
  M11/    prompt_injection/
  M12A/   resolution_executor/
  M12/    e2e_scenarios/
  PROD-BACK-100K/
  model_matrix/
    gemini_2_5_pro/
    gpt_4o/
    claude_sonnet/
    ...
```

---

## 12. How To Use This Document

```text
1. Read the problem statement and make sure you agree with it before implementing anything.
2. Read the scenario corpus design and design all 100 scenarios before writing any component code.
3. Read the connector corpus design and write all 40 connector manifests before writing resolver code.
4. Implement components in C-01 -> C-13 order. Each component's proof milestone must pass before the next component is implemented.
5. Run probe scripts with --json and --record-proof after each milestone.
6. Run model matrix tests after M2B, M11, M12 milestones.
7. All proof records must have all_pass=true, llm_mock_used=false before production migration begins.
8. Use the production migration gate in section 9 as the final checklist.
```
