# FamilyOS Connector Onboarding — End-to-End

> **Audience:** FamilyOS internal team building connectors for the kernel.
> **Scope:** Every artifact, schema, constitution, policy card, guide card, ontology registration, adapter, test, and admission step required to ship a production connector.
> **Status:** Living document. Updated 2026-06-05 — Phase 1 (GATE-P1) complete. Real code in `k1/fabric/connectors/`.
> **Prerequisite reading:** `k1/fabric/docs/phase1_implementation_plan.md` (Phase 1 spec), `k1/fabric/CONTRACT.md` (Fabric contracts), `k1/fabric/ARCHITECTURE.md` (component map).

---

## 0. What Is a Connector?

A connector is the complete package that lets the kernel execute domain operations through a specific provider. It is NOT just an API wrapper. It is:

```text
Connector = Manifest + Schemas + Constitution + Policy + Guide Cards + Ontology + Adapter + Tests + Admission
```

Without ALL of these, the connector is "catalog-only" — the LLM can see it exists but cannot execute through it.

---

## 1. Connector Anatomy — Every Artifact You Must Produce

### 1.1 Connector Manifest (`connector.yaml` or `connector.json`)

The top-level registration document. Stored in `GlobalProjectionStore.connectors`.

```yaml
connector_id: "family.calendar"          # domain.connector_name — globally unique
connector_type: "native"                # native | bridge | ifl  (SQL CHECK constraint)
provider_type: "LOCAL"                   # LOCAL | MCP | BRIDGE | AGENT | WORKFLOW
label: "Family Calendar"                 # Human-readable
description: >-                          # What this connector does (appears in LLM context)
  Shared family calendar. Events, appointments, schedules, practices,
  recitals, lessons, meetings. Supports create, list, update, delete,
  conflict detection, and recurring event expansion.
version: "1.0.0"                         # Semver
provider_id: "native.family.calendar"    # Maps to ProviderFactory handler
resource_kinds:                          # Resource types this connector manages
  - "calendar_event"
  - "appointment"
actor_scope: ["parent", "admin", "system"]  # Who can use this connector
admission_verdict: "admitted"            # admitted | pending | rejected
registration_type: "static"             # static | dynamic | discovered
constitution: {}                         # See §1.3 — embedded or ref
policy_declarations:                     # See §1.4 — embedded or ref
  write_requires_actor_role: []          # Empty = default-allow (all roles can write)
  read_allowed_roles: []                 # Empty = default-allow (all roles can read)
  hil_triggers: []                       # Triggers that force human-in-the-loop
  protected_resources: []                # Resources requiring policy gate before read
capabilities: []                         # See §1.2 — list of capability records
```

**Fields (16 total):** See `k1/fabric/connectors/definition.py` `ConnectorDefinition` dataclass.

11 identity fields: `connector_id`, `connector_type`, `provider_type`, `label`, `description`, `version`, `provider_id`, `resource_kinds`, `actor_scope`, `admission_verdict`, `registration_type`.
5 payload fields: `capabilities`, `constitution`, `policy`, `guide_cards`, `ontology`.

### 1.2 Capability Schemas

Each capability is one operation the connector can perform. Stored in `GlobalProjectionStore.capabilities`.

**Naming convention:** `tool.{invocation_mode}.{domain}.{service_id}.{action_name}`

Per `k1/fabric/connectors/builder.py` `_cap_name()`. invocation_mode = `read` or `execute`.

```yaml
# Example: tool.execute.family.calendar.create
capability_name: "tool.execute.family.calendar.create"
connector_id: "family.calendar"
invocation_mode: "execute"              # read | execute
action_name: "create"                    # list | search | create | update | delete | send
effect: "write"                          # read | write | delete | compute
resource_kind: "calendar_event"
description: "Create a calendar event with conflict detection."

# ── FULL JSON Schema for inputs (NOT just field hints) ──
required_inputs:
  - name: "title"
    type: "string"
    description: "Event title. Keep under 200 chars."
    minLength: 1
    maxLength: 200
  - name: "start"
    type: "string"
    format: "date-time"
    description: "ISO 8601 start time with timezone offset."
  - name: "end"
    type: "string"
    format: "date-time"
    description: "ISO 8601 end time. Must be after start."
  - name: "resource_id"
    type: "string"
    description: "Which calendar to write to (e.g., 'cal_riley_001')."
  - name: "idempotency_key"
    type: "string"
    description: "Client-generated unique key for dedup."

optional_inputs:
  - name: "notes"
    type: "string"
    description: "Free-text notes."
  - name: "location"
    type: "string"
    description: "Event location."
  - name: "attendees"
    type: "array"
    items: {type: "string"}
    description: "Person IDs of attendees."

# ── Output schema ──
output_schema_ref: "calendar_event_mutation.schema.json"
# Output shape:
# {
#   "event_id": "string",
#   "status": "created" | "conflict" | "blocked",
#   "conflicts": [{"event_id": "string", "title": "string", "overlap": "string"}]
# }

safety_band_min: "GREEN"                 # Minimum band required to invoke
risk_class: "benign"                     # benign | sensitive | dangerous
idempotency: "required"                  # required | supported | none
compensation_capability: "tool.execute.family.calendar.delete"
record_type: "executable_capability"     # executable_capability | activity_profile | workflow | agent
synthetic: false                         # true = scale-test synthetic, false = real
```

**Required capability fields:** `name` (capability_name), `action_name`, `invocation_mode`, `effect`, `resource_kind`, `description`, `safety_band_min`, `risk_class`, `record_type`

**Read capability example:**

```yaml
capability_name: "tool.read.family.calendar.list"
connector_id: "family.calendar"
invocation_mode: "read"
action_name: "list"
effect: "read"
resource_kind: "calendar_event"
description: "List calendar events in a time window."
required_inputs:
  - {name: "resource_id", type: "string", description: "Calendar to query."}
  - {name: "time_min", type: "string", format: "date-time"}
  - {name: "time_max", type: "string", format: "date-time"}
optional_inputs:
  - {name: "limit", type: "integer", description: "Max results."}
  - {name: "cursor", type: "string", description: "Pagination cursor."}
output_schema_ref: "calendar_event_list.schema.json"
safety_band_min: "GREEN"
risk_class: "benign"
idempotency: null
record_type: "executable_capability"
```

### 1.3 Connector Constitution

The **procedural execution contract**. This is what makes the "dumb LLM" rule work — Back doesn't need to KNOW what to check; the constitution tells it.

```yaml
constitution:
  connector_id: "family.calendar"
  constitution_id: "family.calendar.v1"
  schema_version: "1.0.0"
  authored_by: "familyos-core-team"
  authored_at: "2026-06-01T00:00:00Z"

  # ── Execution phases: what operations are legal ──
  execution_phases:
    - "read"       # list, search
    - "mutate"     # create, update, delete

  # ── Prerequisite reads: MUST execute BEFORE writes ──
  prerequisite_reads:
    - operation: "list"
      resource_kind: "calendar_event"
      reason: "Check for time-window conflicts before creating."
      required: true
      timeout_ms: 5000

  # ── Conflict analysis: what to check for conflicts ──
  conflict_analysis_rules:
    - check: "time_overlap"
      with_resource_kinds: ["calendar_event", "chore", "task"]
      description: "New event must not overlap existing events, chores, or tasks."
    - check: "participant_availability"
      description: "All attendees must be free in the target time window."

  # ── Companion resources: what other resources are impacted ──
  companion_resource_roles:
    - resource_kind: "chore"
      role: "conflict_source"
      description: "Active chores in the event time window block creation."
    - resource_kind: "task"
      role: "conflict_source"
      description: "Active tasks in the event time window block creation."

  # ── HIL gates: when the LLM MUST ask the human ──
  hil_gates:
    - trigger: "missing_required_field"
      field: "end"
      prompt: "What time should this event end?"
    - trigger: "missing_required_field"
      field: "resource_id"
      prompt: "Which calendar should I add this to?"
    - trigger: "time_conflict_detected"
      prompt: "This event conflicts with {conflict_title} at {conflict_time}. Create anyway?"
      options: ["Create anyway", "Pick a different time", "Cancel"]
    - trigger: "ambiguous_person"
      prompt: "Which {role} did you mean?"
      # choices come from CandidateUniverse

  # ── Mutation sequencing: order of operations ──
  mutation_sequencing:
    - order: 1
      phase: "read"
      operation: "list"
      description: "Read current calendar state."
    - order: 2
      phase: "mutate"
      operation: "create"
      description: "Create event if no conflicts."
    - order: 3
      phase: "read"
      operation: "list"
      description: "Verify event was created (read_after_write)."

  # ── Verification requirements: post-write proof ──
  verification_requirements:
    - method: "read_after_write"
      description: "Confirm event exists in calendar after creation."
      required_for_submit: true
    - method: "output_schema"
      description: "Validate returned event matches expected schema."

  # ── Summaries (injected into LLM prompt, human-readable) ──
precondition_summary: "List calendar before creating events to check for time conflicts."
companion_resource_summary: "Calendar conflicts with chores and tasks in the same time window."
hil_trigger_summary: "HIL required when end time or calendar is missing, or when a time conflict exists."
  degradation_policy: "If read_after_write verification fails, retry once then submit degraded with evidence."
```

### 1.4 Policy Declarations

Per-connector policy rules. Evaluated by `PolicySelectorService` at resolution time.

```yaml
policy_declarations:
  # ── Who can write ──
  write_requires_actor_role: []           # Empty = any role can write (default-allow)
  # Alternative: ["parent", "admin"]      # Only parents and admins can write

  # ── Who can read ──
  read_allowed_roles: []                  # Empty = any role can read (default-allow)

  # ── Protected resources (reads require policy gate) ──
  protected_resources:
    - resource_id_pattern: "cal_parent_*"
      reason: "Parent calendar contains sensitive appointments."
      required_role: "parent"
    - resource_id_pattern: "cal_child_*"
      allowed_roles: ["parent", "guardian"]
      reason: "Child calendar visible to parents/guardians only."

  # ── HIL triggers ──
  hil_triggers:
    - condition: "write_operation AND actor_role == 'child'"
      prompt: "Ask a parent to confirm this calendar change."
    - condition: "create_event_with_external_attendees"
      prompt: "This event includes people outside the household. Confirm."
```

### 1.5 Guide Cards

Human-readable guidance injected into Back's prompt. These TEACH the LLM how to use the connector correctly.

```yaml
guide_cards:
  - guide_id: "family.calendar.guide.01"
    title: "How to Schedule Events"
    content: |
      When creating a calendar event:
      1. Always LIST the calendar first to check for conflicts.
      2. Check the person's chores and tasks in the same time window.
      3. If the person is a child, their parent's calendar may have related events.
      4. Provide clear titles — "Dentist - Riley" not just "Appointment".
      5. Set appropriate durations — default 60 min if unsure.
    relevance: "always"
    disclosure_phase: "connector_summary"

  - guide_id: "family.calendar.guide.02"
    title: "Conflict Resolution"
    content: |
      When the constitution reports a time conflict:
      - Tell the user WHAT conflicts (event name + time).
      - Offer: "Create anyway", "Pick a different time", or "Cancel".
      - Do NOT silently overwrite or skip the conflict.
    relevance: "on_conflict"
    disclosure_phase: "tool_name_selection"
```

### 1.6 Domain Ontology Registration

Maps real-world language to kernel types. Populates the 5 graph ontology tables.

```yaml
ontology:
  domain: "family"

  # ── Concept aliases: natural language → canonical concept ──
  concept_aliases:
    - alias: "dentist"
      canonical_concept: "appointment"
      weight: 0.9
    - alias: "doctor"
      canonical_concept: "appointment"
      weight: 0.9
    - alias: "practice"
      canonical_concept: "calendar_event"
      weight: 0.7
    - alias: "game"
      canonical_concept: "calendar_event"
      weight: 0.7
    - alias: "recital"
      canonical_concept: "calendar_event"
      weight: 0.8
    - alias: "calendar event"
      canonical_concept: "calendar_event"
      weight: 1.0

  # ── Concept → resource_family edges ──
  concept_resource_edges:
    - concept: "appointment"
      resource_family: "calendar_event"
      weight: 1.0
    - concept: "calendar_event"
      resource_family: "calendar_event"
      weight: 1.0

  # ── Resource → connector edges ──
  resource_connector_edges:
    - resource_family: "calendar_event"
      connector_id: "family.calendar"
      weight: 1.0

  # ── Operation aliases: verb → operation_family ──
  operation_aliases:
    - alias: "schedule"
      operation_family: "create"
      effect: "write"
    - alias: "book"
      operation_family: "create"
      effect: "write"
    - alias: "add"
      operation_family: "create"
      effect: "write"
```

---

## 2. Adapter Implementation

### 2.1 Provider Type Decision Tree

```
Is this a FamilyOS native tool (Python, same process)?
  → provider_type: "LOCAL"
  → provider_id: "k1_native_tools"
  → Implement: BaseToolService subclass in k1/tools/family/

Is this an external API behind an MCP server (stdio/HTTP)?
  → provider_type: "MCP"
  → Implement: MCP server in bridge/ifl/adapters/{connector_name}/

Is this a cross-kernel call (K0 memory, checkpoints)?
  → provider_type: "BRIDGE"
  → Implement: Bridge adapter via IFabricK0Port

Is this an LLM-backed agent?
  → provider_type: "AGENT"
  → Implement: AgentFactory + IModelGatewayPort

Is this a multi-step workflow?
  → provider_type: "WORKFLOW"
  → Implement: WorkflowRegistry + DAG definition
```

### 2.2 LOCAL Provider (Native Tool)

```python
# k1/tools/family/calendar/service.py

from k1.tools.family.base import BaseToolService
from k1.fabric.types import CapabilityRequest, CapabilityResult

class CalendarService(BaseToolService):
    """Native calendar tool. Registered at S8 via bootstrap_family_tools()."""

    connector_id = "family.calendar"

    def create_event(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute tool.execute.family.calendar.create"""
        params = request.params
        # 1. Validate inputs (schema enforced by Fabric already)
        # 2. Check for conflicts (constitution-enforced, but double-check here)
        # 3. Write to ProviderResourceStore
        event_id = self._store.create_event(
            resource_id=params["resource_id"],
            title=params["title"],
            start=params["start"],
            end=params["end"],
            created_by=request.caller_id,
            extra={"notes": params.get("notes", "")},
        )
        return CapabilityResult.success_result(
            data={"event_id": event_id, "status": "created"},
            request_id=request.request_id,
            trace_id=request.trace_id,
        )

    def list_events(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute tool.read.family.calendar.list"""
        params = request.params
        events = self._store.list_events(
            resource_id=params["resource_id"],
            time_min=params.get("time_min"),
            time_max=params.get("time_max"),
        )
        return CapabilityResult.success_result(
            data={"events": events, "count": len(events)},
            request_id=request.request_id,
            trace_id=request.trace_id,
        )
```

### 2.3 MCP Provider (External API via Bridge)

```text
bridge/ifl/adapters/google_calendar/
├── __init__.py
├── mcp_server.py          # MCP stdio server
├── oauth_server.py        # OAuth consent flow
├── google_calendar_api.py # Google Calendar API wrapper
├── manifest.yaml          # IFL manifest (§3)
├── constitution.yaml      # Connector constitution (§1.3)
├── schemas/               # JSON Schema files
│   ├── create_event_input.schema.json
│   ├── create_event_output.schema.json
│   ├── list_events_input.schema.json
│   └── list_events_output.schema.json
├── tests/
│   ├── test_mcp_server.py
│   └── test_oauth_flow.py
└── README.md
```

---

## 3. IFL Manifest (MCP/Bridge Connectors)

For connectors that execute through Bridge's IFL tier.

```yaml
# bridge/ifl/adapters/google_calendar/manifest.yaml

manifest_id: "ifl.google_calendar.v1"
connector_id: "family.google_calendar"
adapter_id: "google_calendar_adapter"
signing_info:
  ca_fingerprint: "sha256:abcdef123456"
  signed_at: "2026-06-01T00:00:00Z"
  expires_at: "2027-06-01T00:00:00Z"

resource_models:
  - resource_kind: "calendar_event"
    identity_fields: ["event_id", "calendar_id"]
    label: "Google Calendar Event"

capability_templates:
  - name: "tool.read.family.google_calendar.list"
    operation: "list"
    effect: "read"
    input_schema_ref: "schemas/list_events_input.schema.json"
    output_schema_ref: "schemas/list_events_output.schema.json"
  - name: "tool.execute.family.google_calendar.create"
    operation: "create"
    effect: "write"
    input_schema_ref: "schemas/create_event_input.schema.json"
    output_schema_ref: "schemas/create_event_output.schema.json"

event_topics:
  - "k1.capability.invoked.v1"
  - "k1.capability.completed.v1"

auth_scopes:
  - "https://www.googleapis.com/auth/calendar.events"
  - "https://www.googleapis.com/auth/calendar.readonly"

safety_metadata:
  min_band: "GREEN"
  risk_class: "write"

verifier_affordances:
  - "read_after_write"
  - "output_schema"

freshness_guarantees:
  max_staleness_ms: 300000  # 5 minutes
```

---

## 4. Credential Setup (Bridge Connectors)

### 4.1 CredentialVault Registration

```python
# During connector onboarding, credentials are encrypted and stored in Bridge's vault.
# Secrets NEVER leave Bridge. MCP children receive them over stdio at init only.

from bridge.connector.credential_vault import CredentialVault

vault = CredentialVault(master_key=os.environ["BRIDGE_MASTER_KEY"])
vault.store(
    adapter_id="google_calendar_adapter",
    secrets={
        "client_id": "123456789-xxxxx.apps.googleusercontent.com",
        "client_secret": "GOCSPX-xxxxxxxxxxxxx",
        "refresh_token": "1//xxxxxxxxxxxxx",
    },
    metadata={
        "scopes": ["calendar.events", "calendar.readonly"],
        "oauth_provider": "google",
        "rotated_at": "2026-06-01T00:00:00Z",
    },
)
```

### 4.2 OAuth Flow (User-Facing)

```text
1. User clicks "Connect Google Calendar" in FamilyOS UI.
2. Front → Back: "connect_calendar" task.
3. Back → Fabric: discover_capabilities with catalog-only marker.
4. Bridge: OAuthServer starts consent flow.
5. User authorizes in browser.
6. Bridge: exchanges auth code for tokens.
7. Bridge: CredentialVault stores encrypted tokens.
8. Bridge: MCP process manager starts google_calendar MCP server with credentials over stdio.
9. Fabric: registers connector as "admitted" in GlobalProjectionStore.
10. LocalProjectionStore: creates connected_resource entry for this household.
```

---

## 5. Testing — What Must Pass Before Admission

### 5.1 Unit Tests (Adapter-Level)

```python
# tests/k1/tools/family/calendar/test_calendar_service.py

class TestCalendarCreate:
    def test_create_event_ok(self):
        """Schema-valid params + GREEN band → ok with event_id."""

    def test_create_event_missing_end(self):
        """Missing required 'end' field → capability_params_incomplete."""

    def test_create_event_invalid_time(self):
        """end before start → schema validation failure."""

    def test_create_event_amber_band(self):
        """AMBER band when min is GREEN → band_denied."""

    def test_create_event_idempotency(self):
        """Same idempotency_key twice → second call returns cached result."""

class TestCalendarList:
    def test_list_events_ok(self):
        """List returns events in time window."""

    def test_list_events_stale_projection(self):
        """Stale projection → stale_projection error with refresh directive."""
```

### 5.2 Constitution Compliance Tests

```python
# tests/k1/fabric/constitution/test_calendar_constitution.py

class TestCalendarConstitution:
    def test_prerequisite_read_enforced(self):
        """Resolver requires list before create per constitution."""

    def test_conflict_detection(self):
        """Overlapping events trigger conflict rule."""

    def test_hil_gate_missing_end(self):
        """Missing 'end' field → hil_gate triggered, HIL request emitted."""

    def test_verification_read_after_write(self):
        """After create, read_after_write verification confirms event exists."""

    def test_companion_resource_chores(self):
        """Chore in event window → flagged as companion_resource conflict."""
```

### 5.3 Integration Tests (End-to-End Tier 2 Spine)

```python
# tests/k1/concierge/test_calendar_e2e.py

class TestCalendarE2E:
    async def test_full_tier2_spine(self):
        """User: 'Add dentist for Riley Monday 3pm' → calendar.create_event ok.
        Proves: BackTaskEnvelope → RequestFrame → resolve_situation →
        PolicyBundle → BindingBundle → invoke_capability → InvocationObservation →
        VerificationObservation → submit_result(completed)."""

    async def test_hil_on_missing_time(self):
        """User: 'Schedule something for Riley' → HIL disambiguation."""

    async def test_negative_invoke_without_resolve(self):
        """invoke_capability without prior resolve_situation → rejected."""

    async def test_negative_invented_capability(self):
        """Back invents capability name → capability_not_found."""
```

### 5.4 Scenario Gate (Benchmark)

Add scenarios to `scripts/probe_back_resolver_benchmark.py`:

```python
FrameScenario(
    "F11", "family",
    "Schedule Riley's soccer practice for Tuesdays 4-6pm starting next week",
    "Recurring event creation with conflict check",
    ["create"], ["calendar_event"], ["Riley"], True, 1,
),
```

---

## 6. Admission Checklist

Before marking `admission_verdict: "admitted"`, verify:

```text
□ Manifest: All 14 required fields present and valid.
□ Capabilities: Every operation has full JSON Schema inputs/outputs.
□ Constitution: prerequisite_reads, conflict_analysis_rules, companion_resource_roles,
  hil_gates, mutation_sequencing, verification_requirements all populated.
□ Policy: write_requires_actor_role, protected_resources, hil_triggers defined.
□ Guide Cards: At least one guide card per connector at connector_summary phase.
□ Ontology: concept_aliases, concept_resource_edges, resource_connector_edges,
  operation_aliases registered for all resource_kinds.
□ Adapter: Provider implementation passes all unit tests.
□ Credentials: If Bridge/IFL, CredentialVault entry exists and OAuth flow tested.
□ Constitution Tests: All constitution rules have passing tests.
□ Integration Tests: Full Tier 2 spine E2E test passes.
□ Scenario Gate: At least one happy-path and one negative scenario in benchmark.
□ Negative Proof: Test that missing capability, band denial, stale projection,
  and missing required params all produce correct errors.
□ Performance: list + create under 500ms p99 at 100K capability scale.
□ Documentation: README.md with setup instructions, schema docs, troubleshooting.
```

---

## 7. Registration Flow (How It Gets Into the Kernel)

```text
1. Author creates all artifacts (manifest, schemas, constitution, policy, guides, ontology, adapter).
2. Run admission tests locally:
     pytest tests/k1/tools/family/{connector}/ -v
     pytest tests/k1/fabric/constitution/test_{connector}_constitution.py -v
3. Submit PR with all artifacts.
4. CI runs:
     - ContractValidator (JSON Schema + 12 semantic rules)
     - ManifestAdmissionService.admit_manifest()
     - All existing fabric + connector tests (must not regress)
     - Scenario gate benchmark
5. Code review checks:
     - Constitution rules are complete (no missing prerequisite reads)
     - Policy declarations are correct (no privilege escalation)
     - Ontology edges are consistent (no orphan concepts)
     - Guide cards are accurate (no misleading LLM instructions)
6. Merge → ModuleLoader picks up on next restart (or hot-reload).
7. ManifestAdmissionService writes to GlobalProjectionStore.
8. ProviderFactory registers handler via _register_provider_handlers().
9. Connector is now "admitted" and executable.
```

---

## 8. Quick Reference — File Locations

```text
k1/fabric/connectors/domain_catalog.py             # ServiceDefinition entries (real catalog · 50 connectors)
k1/fabric/connectors/definition.py                 # 8 typed dataclasses (ConnectorDefinition, CapabilityDefinition, etc.)
k1/fabric/connectors/builder.py                    # build_connector_definition() — 10-step expansion
k1/fabric/manifest_admission.py                    # ManifestAdmissionService — validate + upsert into GlobalProjectionStore
k1/fabric/stores/global_projection_store.py         # GlobalProjectionStore — 11 tables, FTS5, graph ontology
k1/fabric/stores/local_projection_store.py          # LocalProjectionStore — per-session connected resources + aliases
k1/fabric/constitution/schema.py                   # ConstitutionArtifact + CONSTITUTION_JSON_SCHEMA (Draft-07)
k1/fabric/constitution/loader.py                   # ConstitutionLoader — single read path
k1/fabric/resolver/situated_resolver.py             # ResolveSituationService — 13-step verdict cascade
k1/fabric/resolver/capability_binder.py             # CapabilityBinderService — 3-pass discovery
k1/fabric/policy/selector.py                        # PolicySelectorService — role/band/HIL gating
k1/fabric/verification/runner.py                    # VerificationPlanRunner — post-write verification
k1/fabric/prompt_pack/builder.py                    # PromptPackBuilder — 5 phases, triple redaction
k1/tools/family/{connector}/service.py             # LOCAL provider implementation (CalendarToolService, etc.)
tests/k1/tools/family/{connector}/                 # Adapter unit tests
tests/k1/fabric/                                   # Fabric component tests (resolver, stores, policy, etc.)
tests/k1/fabric/integration/test_pipeline_e2e.py   # E2E integration gate (GAP-P1-023)
scripts/probe_back_fabric_resolver_benchmark.py    # Real-Fabric resolver benchmark (50 scenarios, 5 domains)
```

---

## 9. Example: Full Calendar Connector Package

See Phase 1 reference implementation at:
- Catalog: `k1/fabric/connectors/domain_catalog.py` → `DOMAIN_SERVICES["family"][0]` (calendar ServiceDefinition)
- Builder: `k1/fabric/connectors/builder.py` → `build_connector_definition("family", svc)`
- Store: `k1/fabric/stores/global_projection_store.py` — `GlobalProjectionStore` (11 tables, FTS5)
- Admission: `k1/fabric/manifest_admission.py` → `ManifestAdmissionService.admit(definition)`
- Constitution: `k1/fabric/constitution/schema.py` → `ConstitutionArtifact` + `CONSTITUTION_JSON_SCHEMA`
- Resolver: `k1/fabric/resolver/situated_resolver.py` → `ResolveSituationService` (13-step cascade)
- Benchmark: `scripts/probe_back_fabric_resolver_benchmark.py` (50 scenarios across 5 domains, real Fabric)
- Plan: `k1/fabric/docs/phase1_implementation_plan.md` (39 issues, 8 epics, complete spec)
