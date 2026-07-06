# External Connector Development — End-to-End Guide

> **Audience:** External companies, 3rd-party developers, and independent contributors building connectors for the FamilyOS kernel.
> **Scope:** Everything an external team needs to design, build, test, submit, and maintain a production connector. No FamilyOS internal knowledge assumed.
> **Status:** Living document. Updated 2026-06-05 — Phase 1 (GATE-P1) complete. Real code in `k1/fabric/connectors/`.
> **Prerequisite reading:** `connector_onboarding_familyos.md` (internal guide), `k1/fabric/docs/phase1_implementation_plan.md` (Phase 1 spec), `k1/fabric/CONTRACT.md` (Fabric contracts).

---

## 0. What You're Building

A **connector** is a plugin that lets the FamilyOS kernel execute operations through your service. If you build a Google Calendar connector, FamilyOS users can say "add dentist appointment Tuesday 3pm" and the kernel will schedule it on their Google Calendar — with conflict detection, policy enforcement, and verification built in.

Your connector is NOT just an API wrapper. The kernel requires these artifacts from you:

```text
Your Connector = IFL Manifest + JSON Schemas + Constitution + Adapter Code + Credential Setup + Tests
```

You do NOT need to understand the kernel internals. You provide these artifacts in standard formats, and the kernel handles resolution, policy, binding, prompt injection, and the LLM ReAct loop.

---

## 1. The Contract — What You Provide vs. What the Kernel Does

### You Provide (External)

| Artifact | Format | Purpose |
|----------|--------|---------|
| IFL Manifest | YAML | Declares connector identity, capabilities, auth scopes |
| JSON Schemas | JSON Schema Draft-07 | Input/output shapes for every operation |
| Connector Constitution | YAML | Procedural rules: what to check before writes, conflicts, HIL gates |
| Adapter Code | Python MCP server | Actual implementation — talks to your API |
| OAuth/Credential Setup | Environment + Bridge vault | How the kernel authenticates to your service |
| Tests | pytest | Prove your connector works correctly |

### The Kernel Provides (You Don't Build)

| Kernel Component | What It Does For You |
|-----------------|---------------------|
| `GlobalProjectionStore` | Stores your manifest, capabilities, constitution — 11 tables + FTS5 search (BM25) |
| `LocalProjectionStore` | Per-session store tracking connected resources, household members, aliases |
| `ManifestAdmissionService` | Typed validation + idempotent upsert into GlobalProjectionStore |
| `CapabilityTypeResolver` | 4-step graph traversal — maps user language to typed capabilities via capability_type_index |
| `PolicySelectorService` | Gates on typed ResolvedIntentType — role checks, safety bands, HIL triggers; deterministic (no eval) |
| `CapabilityBinderService` | 3-pass discovery (typed graph → exact match → BM25 FTS5) → BindingBundle |
| `ResolveSituationService` | 13-step verdict cascade → ResolutionEnvelope {verdict, binding_bundle, prompt_pack} |
| `PromptPackBuilder` | 5 disclosure phases, triple redaction check against SECRET_MARKERS — any leak raises PromptPackLeakError |
| `ConstitutionLoader` | Single read path — loads typed ConstitutionArtifact validated via JSON Schema Draft-07 |
| `VerificationPlanRunner` | Post-write verification (read_after_write / output_schema) via NativeReadbackPort |
| `IdempotencyStore` | State machine: not_seen→in_flight→succeeded/failed; succeeded is immutable |
| `FabricFactory` | STEP 21 wires all Phase 1 components (gated on enable_fabric_stores=True) |
| `GlobalProjectionStore` | Phase 2.6 taxonomy tables (`domains`, `resource_families`, `domain_resource_families`, `connector_resource_families`) — governs which domains and resource families exist |

---

## 1a. Domain & Resource Family Taxonomy

Before you write your manifest, you need to know which **domain** your connector belongs to and which **resource families** it manages. These are governed by the FamilyOS taxonomy — a set of SQLite tables that every connector must align with.

### What Is a Domain?

A **domain** is the broadest category your connector operates in. FamilyOS defines 16 domains:

| Domain | Label | Example Connectors |
|--------|-------|--------------------|
| `family` | Family & Household | Calendar, Tasks, Chores, Shopping, Reminders, Family Settings |
| `health` | Health & Wellness | Fitbit, Apple Health, MyFitnessPal, CVS Pharmacy |
| `finance` | Banking & Finance | Chase, Plaid, Mint, TurboTax |
| `education` | Education & Learning | Canvas, Google Classroom, Duolingo |
| `productivity` | Work & Productivity | Notion, Todoist, Google Docs |
| `home` | Smart Home & Living | Nest, Philips Hue, Ring |
| `transport` | Transport & Travel | Uber, Lyft, Delta, Marriott |
| `food` | Food & Cooking | Instacart, HelloFresh, Yummly |
| `fitness` | Fitness & Activity | Strava, Peloton, Whoop |
| `entertainment` | Media & Entertainment | Netflix, Spotify, Steam |
| `communication` | Messaging & Social | WhatsApp, Slack, Discord |
| `government` | Government & Civic | DMV, IRS, USPS |
| `legal` | Legal & Compliance | DocuSign, LexisNexis |
| `utilities` | Utilities & Services | PG&E, Comcast, Verizon |
| `agriculture` | Agriculture & Farming | John Deere, Climate FieldView |
| `automotive` | Automotive & Vehicles | Tesla, Carfax, Geico |

Your connector's domain determines its `connector_id` prefix: `{domain}.{your_connector_name}`. Example: `family.acme_calendar`.

**You cannot create a new domain.** Domains are governed by the FamilyOS team. If you believe a new domain is needed, see `RESOURCE_FAMILY_TAXONOMY.md` §6.

### What Is a Resource Family?

A **resource family** names the real-world kind of thing your connector operates on. It is NOT an implementation detail — it's a governed taxonomy term. Multiple connectors in the same domain can share a family.

| Good (real-world concept) | Bad (implementation detail) |
|---------------------------|----------------------------|
| `event` | `calendar_event` |
| `item` | `shopping_list_entry` |
| `account` | `chase_checking_account` |
| `prescription` | `cvs_medication_refill` |

The **`family`** domain has these families: `chore`, `contact`, `event`, `item`, `meal`, `message`, `notification`, `pet`, `recipe`, `record`, `reminder`, `setting`, `subscription`, `task` (14 total).

The full list of 57 families across all 16 domains is in `RESOURCE_FAMILY_TAXONOMY.md` §2-3.

### How This Affects Your Manifest

Your IFL manifest's `connector_id` MUST use a valid domain prefix. Your `resource_models` MUST list `resource_kind` values that correspond to valid resource families. When you submit for admission, the kernel validates these against the taxonomy tables.

**Manifest example with taxonomy fields:**

```yaml
connector_id: "family.acme_calendar"    # ← domain prefix MUST be a valid domain
adapter_id: "acme_calendar_adapter"

# Taxonomy declaration (Phase 2.6+):
domain_id: "family"                     # ← matches connector_id prefix
resource_families: ["event"]            # ← from the family domain's approved list

resource_models:
  - resource_kind: "calendar_event"     # ← your connector-specific kind
    # This maps to taxonomy family_id="event" via resource_families above
```

### Finding the Right Family

1. Check `RESOURCE_FAMILY_TAXONOMY.md` §2-3 for the full domain→family mapping.
2. Pick your domain from §1 of that document.
3. Find families in your domain that match what your connector manages.
4. If no existing family fits, you can propose a new one (see §6 of the taxonomy doc).
5. Set `resource_families` to the taxonomy family IDs, and `resource_kind` to your connector-specific name.

---

## 2. Step-by-Step: Build Your Connector

### Step 1: Define Your Operations

What can users DO through your connector? List every operation.

```text
Example: Google Calendar Connector
  - list_events     → "What's on my calendar this weekend?"
  - create_event    → "Add dentist appointment Tuesday 3pm"
  - update_event    → "Move the team meeting to Thursday"
  - delete_event    → "Cancel the weekly standup"
```

### Step 2: Write Your IFL Manifest

This is the single YAML file that declares your connector to the kernel.

```yaml
# manifest.yaml — place in bridge/ifl/adapters/{your_connector}/manifest.yaml

manifest_id: "ifl.acme_calendar.v1"
connector_id: "family.acme_calendar"      # domain.your_company_connector
adapter_id: "acme_calendar_adapter"
signing_info:
  ca_fingerprint: "sha256:YOUR_CA_FINGERPRINT"
  signed_at: "2026-06-01T00:00:00Z"
  expires_at: "2027-06-01T00:00:00Z"

# ── What resources does your connector manage? ──
resource_models:
  - resource_kind: "calendar_event"
    identity_fields: ["event_id", "calendar_id"]
    label: "Calendar Event"
    description: "A scheduled event on the user's calendar."

# ── What operations are available? ──
capability_templates:
  - name: "tool.read.family.acme_calendar.list"
    invocation_mode: "read"
    action_name: "list"
    effect: "read"
    resource_kind: "calendar_event"
    description: "List calendar events in a time window."
    input_schema_ref: "schemas/list_events_input.schema.json"
    output_schema_ref: "schemas/list_events_output.schema.json"

  - name: "tool.execute.family.acme_calendar.create"
    invocation_mode: "execute"
    action_name: "create"
    effect: "write"
    resource_kind: "calendar_event"
    description: "Create a new calendar event."
    input_schema_ref: "schemas/create_event_input.schema.json"
    output_schema_ref: "schemas/create_event_output.schema.json"

  - name: "tool.execute.family.acme_calendar.update"
    invocation_mode: "execute"
    action_name: "update"
    effect: "write"
    resource_kind: "calendar_event"
    description: "Update an existing calendar event."
    input_schema_ref: "schemas/update_event_input.schema.json"
    output_schema_ref: "schemas/update_event_output.schema.json"

  - name: "tool.execute.family.acme_calendar.delete"
    invocation_mode: "execute"
    action_name: "delete"
    effect: "write"
    resource_kind: "calendar_event"
    description: "Delete a calendar event."
    input_schema_ref: "schemas/delete_event_input.schema.json"
    output_schema_ref: "schemas/delete_event_output.schema.json"

# ── What event topics does your connector emit? ──
event_topics:
  - "k1.capability.invoked.v1"
  - "k1.capability.completed.v1"

# ── What OAuth scopes does your connector need? ──
auth_scopes:
  - "https://www.googleapis.com/auth/calendar.events"
  - "https://www.googleapis.com/auth/calendar.readonly"

# ── Safety metadata ──
safety_metadata:
  min_band: "GREEN"
  risk_class: "write"

# ── What verification methods do you support? ──
verifier_affordances:
  - "read_after_write"
  - "output_schema"

# ── How fresh is your data? ──
freshness_guarantees:
  max_staleness_ms: 300000  # 5 minutes — events may take up to 5 min to appear
```

### Step 3: Write JSON Schemas

For EVERY operation, provide a complete JSON Schema (Draft-07) for inputs and outputs. These are NOT optional — the kernel validates all params against these schemas before calling your adapter.

```json
// schemas/create_event_input.schema.json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "minLength": 1,
      "maxLength": 200,
      "description": "Event title."
    },
    "start": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 start time with timezone offset."
    },
    "end": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 end time. Must be after start."
    },
    "resource_id": {
      "type": "string",
      "description": "Which calendar to write to."
    },
    "idempotency_key": {
      "type": "string",
      "description": "Unique key for deduplication. Generate with UUID v4."
    },
    "notes": {
      "type": "string",
      "description": "Optional free-text notes."
    },
    "location": {
      "type": "string",
      "description": "Optional event location."
    },
    "attendees": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Optional attendee email addresses."
    }
  },
  "required": ["title", "start", "end", "resource_id", "idempotency_key"],
  "additionalProperties": false
}
```

```json
// schemas/create_event_output.schema.json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "event_id": {
      "type": "string",
      "description": "The provider-assigned event ID."
    },
    "status": {
      "type": "string",
      "enum": ["created", "conflict", "blocked"],
      "description": "Creation status."
    },
    "conflicts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "event_id": {"type": "string"},
          "title": {"type": "string"},
          "overlap": {"type": "string"}
        }
      },
      "description": "Conflicting events, if any."
    }
  },
  "required": ["event_id", "status"],
  "additionalProperties": false
}
```

### Step 4: Write Your Connector Constitution

This is the MOST IMPORTANT artifact. It tells the kernel what your connector requires before/after operations. The LLM does NOT need to "know" your API — the constitution tells it.

```yaml
# constitution.yaml
connector_id: "family.acme_calendar"
constitution_id: "acme_calendar.v1"
schema_version: "1.0.0"
authored_by: "Acme Corp"
authored_at: "2026-06-01T00:00:00Z"

execution_phases:
  - "read"
  - "mutate"

# ── What MUST happen BEFORE a write? ──
prerequisite_reads:
  - operation: "list"
    resource_kind: "calendar_event"
    reason: "Check for time-window conflicts before creating or updating events."
    required: true
    timeout_ms: 5000

# ── What constitutes a conflict? ──
conflict_analysis_rules:
  - check: "time_overlap"
    with_resource_kinds: ["calendar_event"]
    description: "New or updated event must not overlap existing events on the same calendar."

# ── What other resources are impacted? ──
companion_resource_roles:
  - resource_kind: "calendar_event"
    role: "conflict_source"
    description: "Other calendar events in the same time window may conflict."

# ── When should the kernel ask the user for input? ──
hil_gates:
  - trigger: "missing_required_field"
    field: "end"
    prompt: "What time should this event end?"
  - trigger: "missing_required_field"
    field: "resource_id"
    prompt: "Which calendar should I add this to?"
  - trigger: "time_conflict_detected"
    prompt: "This time conflicts with '{conflict_title}'. Create anyway?"
    options: ["Create anyway", "Pick a different time", "Cancel"]

# ── What order should operations happen in? ──
mutation_sequencing:
  - order: 1
    phase: "read"
    operation: "list"
    description: "Read current calendar state."
  - order: 2
    phase: "mutate"
    operation: "create"
    description: "Create the event."
  - order: 3
    phase: "read"
    operation: "list"
    description: "Verify event creation (read_after_write)."

# ── How should the kernel verify writes? ──
verification_requirements:
  - method: "read_after_write"
    description: "After creating, list events to confirm the new event appears."
    required_for_submit: true
  - method: "output_schema"
    description: "Validate returned event against the output schema."

# ── Human-readable summaries (injected into LLM prompt) ──
precondition_summary: "Always list the calendar before creating events to check for time conflicts."
companion_resource_summary: "New events may conflict with existing events in the same time window."
hil_trigger_summary: "HIL required when end time or calendar selection is missing, or when a time conflict exists."
degradation_policy: "If read_after_write verification fails, retry once then submit as degraded."
```

### Step 5: Implement Your MCP Adapter

Your adapter is a Python MCP (Model Context Protocol) server that communicates over stdio. The kernel's Bridge starts your server as a child process and communicates via JSON-RPC over stdin/stdout.

```python
# mcp_server.py — place in bridge/ifl/adapters/{your_connector}/mcp_server.py

import json
import sys
from your_api_client import AcmeCalendarClient

class AcmeCalendarMCPServer:
    """MCP server for Acme Calendar connector. Communicates over stdio."""

    def __init__(self):
        # Credentials are passed via stdin at startup — never via env/argv.
        init_msg = json.loads(sys.stdin.readline())
        self.client = AcmeCalendarClient(
            client_id=init_msg["client_id"],
            client_secret=init_msg["client_secret"],
            refresh_token=init_msg["refresh_token"],
        )

    def run(self):
        """Main loop: read JSON-RPC requests from stdin, write responses to stdout."""
        for line in sys.stdin:
            request = json.loads(line)
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            try:
                if method == "tool.read.family.acme_calendar.list":
                    result = self.list_events(params)
                elif method == "tool.execute.family.acme_calendar.create":
                    result = self.create_event(params)
                elif method == "tool.execute.family.acme_calendar.update":
                    result = self.update_event(params)
                elif method == "tool.execute.family.acme_calendar.delete":
                    result = self.delete_event(params)
                elif method == "health_check":
                    result = {"status": "ok"}
                else:
                    result = {"error": f"Unknown method: {method}"}

                response = {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as e:
                response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -1, "message": str(e)}}

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    def list_events(self, params: dict) -> dict:
        events = self.client.list_events(
            calendar_id=params["resource_id"],
            time_min=params.get("time_min"),
            time_max=params.get("time_max"),
            limit=params.get("limit", 50),
        )
        return {"events": events, "count": len(events)}

    def create_event(self, params: dict) -> dict:
        event = self.client.create_event(
            calendar_id=params["resource_id"],
            title=params["title"],
            start=params["start"],
            end=params["end"],
            notes=params.get("notes"),
            location=params.get("location"),
            attendees=params.get("attendees"),
            idempotency_key=params["idempotency_key"],
        )
        return {"event_id": event["id"], "status": "created"}

    def update_event(self, params: dict) -> dict:
        event = self.client.update_event(
            event_id=params["event_id"],
            calendar_id=params["resource_id"],
            title=params.get("title"),
            start=params.get("start"),
            end=params.get("end"),
        )
        return {"event_id": event["id"], "status": "updated"}

    def delete_event(self, params: dict) -> dict:
        self.client.delete_event(
            event_id=params["event_id"],
            calendar_id=params["resource_id"],
        )
        return {"event_id": params["event_id"], "status": "deleted"}

if __name__ == "__main__":
    server = AcmeCalendarMCPServer()
    server.run()
```

### Step 6: Credential Setup (OAuth)

The kernel's Bridge manages credentials. You provide OAuth endpoints; Bridge handles the flow.

```yaml
# oauth_config.yaml
oauth_provider: "acme"
auth_url: "https://auth.acme.com/oauth2/authorize"
token_url: "https://auth.acme.com/oauth2/token"
scopes:
  - "calendar.read"
  - "calendar.write"
client_registration:
  # How FamilyOS registers as an OAuth client with your service
  redirect_uri: "https://familyos.app/oauth/callback"
  client_id_env: "ACME_CALENDAR_CLIENT_ID"
  client_secret_env: "ACME_CALENDAR_CLIENT_SECRET"
```

During user onboarding, Bridge:

1. Starts OAuth flow → user authorizes in browser
2. Exchanges auth code for tokens
3. Stores encrypted tokens in `CredentialVault` (AES256-GCM)
4. Your MCP server receives tokens over stdio at startup — NEVER via environment variables or command-line arguments

---

## 3. Testing Your Connector

### 3.1 Local MCP Server Test

```python
# tests/test_mcp_server.py
import subprocess
import json

def test_health_check():
    """Start MCP server, send health_check, verify response."""
    proc = subprocess.Popen(
        ["python", "mcp_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    # Send credentials
    proc.stdin.write(json.dumps({"client_id": "test", "client_secret": "test", "refresh_token": "test"}) + "\n")
    proc.stdin.flush()

    # Send health check
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "health_check", "id": 1, "params": {}}) + "\n")
    proc.stdin.flush()

    response = json.loads(proc.stdout.readline())
    assert response["result"]["status"] == "ok"
    proc.terminate()

def test_create_event_schema_validation():
    """Missing required 'end' field → error."""
    # ... send create_event without 'end', expect error response

def test_create_event_ok():
    """Valid params → event created."""
    # ... send valid create_event, expect event_id in response
```

### 3.2 Schema Validation Test

```python
# tests/test_schemas.py
import jsonschema
import json

def test_create_event_input_schema():
    with open("schemas/create_event_input.schema.json") as f:
        schema = json.load(f)

    valid_params = {
        "title": "Team Standup",
        "start": "2026-06-05T09:00:00-05:00",
        "end": "2026-06-05T09:30:00-05:00",
        "resource_id": "cal_primary",
        "idempotency_key": "abc123",
    }
    jsonschema.validate(valid_params, schema)  # Should not raise

    invalid_params = {"title": "Missing required fields"}
    try:
        jsonschema.validate(invalid_params, schema)
        assert False, "Should have raised"
    except jsonschema.ValidationError:
        pass  # Expected
```

### 3.3 Constitution Compliance Test

```python
# tests/test_constitution.py

def test_prerequisite_read_required():
    """Constitution declares list before create. Verify it's in the YAML."""
    import yaml
    with open("constitution.yaml") as f:
        constitution = yaml.safe_load(f)

    prereads = constitution["prerequisite_reads"]
    assert any(r["operation"] == "list" and r["required"] for r in prereads)

def test_verification_read_after_write():
    """Constitution requires read_after_write verification."""
    import yaml
    with open("constitution.yaml") as f:
        constitution = yaml.safe_load(f)

    verifications = constitution["verification_requirements"]
    assert any(v["method"] == "read_after_write" and v["required_for_submit"] for v in verifications)
```

### 3.4 Integration Test (with Kernel)

```python
# tests/test_kernel_integration.py
# Requires a running kernel instance. Set KERNEL_ENDPOINT env var.

async def test_discover_capability():
    """Your connector appears in catalog discovery."""
    # Call Fabric's discover_capabilities with domain="family"
    # Verify your capability names appear in results

async def test_resolve_situation():
    """Your connector produces valid bindings through resolve_situation."""
    # Build RequestFrame for "add dentist appointment Tuesday 3pm"
    # Call resolve_situation
    # Verify BindingBundle contains your capability as primary_write

async def test_invoke_creates_event():
    """Full execution: invoke → event created → verified."""
    # Setup: register test household, connect your calendar
    # invoke create_event
    # Verify InvocationObservation.status == "ok"
    # Verify VerificationObservation.status == "verified"
```

---

## 4. Submission & Admission

### 4.1 Submission Package

Submit a PR with this structure:

```text
bridge/ifl/adapters/{your_connector}/
├── manifest.yaml              # IFL manifest
├── constitution.yaml          # Connector constitution
├── oauth_config.yaml          # OAuth configuration
├── mcp_server.py              # MCP server implementation
├── requirements.txt           # Python dependencies
├── schemas/
│   ├── list_events_input.schema.json
│   ├── list_events_output.schema.json
│   ├── create_event_input.schema.json
│   ├── create_event_output.schema.json
│   ├── update_event_input.schema.json
│   ├── update_event_output.schema.json
│   ├── delete_event_input.schema.json
│   └── delete_event_output.schema.json
├── tests/
│   ├── test_mcp_server.py
│   ├── test_schemas.py
│   └── test_constitution.py
├── README.md                  # Setup instructions, API docs, troubleshooting
└── LICENSE
```

### 4.2 Admission Checklist

Before marking `admission_verdict: "admitted"`, the FamilyOS team verifies:

```text
□ Manifest: All 14 required ConnectorDefinition fields present. connector_id follows naming convention.
□ Capabilities: Every operation has full JSON Schema (Draft-07) input_schema + output_schema.
□ Constitution: prerequisite_reads, conflict_analysis_rules, companion_resource_roles,
  hil_gates, mutation_sequencing, verification_requirements all populated.
  Constitution passes validate_constitution() against CONSTITUTION_JSON_SCHEMA.
□ Adapter: MCP server starts, responds to health_check, handles all declared operations.
□ Error handling: Invalid params → clear error. Timeout → graceful degradation.
□ Credentials: OAuth flow documented. CredentialVault registration tested.
□ Tests pass: pytest tests/ -v (all green).
□ No secrets in code: API keys, tokens, secrets are in CredentialVault only.
  No hardcoded credentials, no env var secrets, no argv secrets.
□ Documentation: README explains setup, OAuth flow, operation descriptions, error codes.
□ Performance: list_events < 2s, create_event < 3s at p95.
□ Idempotency: create_event with same idempotency_key twice → second call returns same event_id.
```
```

### 4.3 Admission Flow

```text
1. You submit PR with complete package.
2. FamilyOS CI runs:
     - ContractValidator: JSON Schema validation (via jsonschema Draft7Validator)
     - ManifestAdmissionService.admit(definition) — typed validation + upsert
     - Automated MCP server integration test
     - Constitution validation via validate_constitution() + validate_constitution_semantics()
     - All existing tests (must not regress — 280 Phase 1 tests)
3. FamilyOS reviewer checks:
     - Constitution rules are complete and correct
     - No security issues (credential handling, input validation)
     - Schemas are well-formed and complete
     - Error handling is robust
     - Documentation is clear
4. If approved:
     - Manifest is signed with FamilyOS CA key
     - CredentialVault entry is created (encrypted)
     - MCP process manager registers your server
     - ManifestAdmissionService writes to GlobalProjectionStore (idempotent upsert)
     - Connector appears in catalog (discover_capabilities + search_capabilities via FTS5)
5. Connector is now "admitted" and executable by all FamilyOS households.
```

---

## 5. Ongoing Maintenance

### 5.1 Versioning

```text
- Follow Semver: MAJOR.MINOR.PATCH
- MAJOR: Breaking schema changes (new required fields, removed operations)
- MINOR: New operations, new optional fields (backward compatible)
- PATCH: Bug fixes, description updates, guide card improvements

When you release a new version:
1. Update manifest.version
2. Update constitution.schema_version
3. Add migration notes if MAJOR
4. Old versions remain executable until explicitly deprecated
```

### 5.2 Deprecation

```text
To deprecate an operation or entire connector:
1. Set admission_verdict: "suspended" in manifest
2. Add deprecation notice to guide cards
3. Existing bindings continue to work for 90 days
4. New resolutions refuse the connector
5. After 90 days: admission_verdict → "rejected"
```

### 5.3 Monitoring

The kernel emits these events for your connector (available in FamilyOS dashboard):

```text
k1.capability.invoked.v1        → Every invocation
k1.capability.completed.v1      → Successful execution
k1.capability.failed.v1         → Failed execution
k1.fabric.provider.health.changed.v1 → Health status changes
```

Metrics available: execution count, latency p50/p95/p99, error rate, success rate 30d.

---

## 6. Reference: Minimal Connector Template

```yaml
# The absolute minimum to get a connector admitted.
# Copy this, fill in your details, implement mcp_server.py.

manifest_id: "ifl.{your_name}.v1"
connector_id: "family.{your_name}"
adapter_id: "{your_name}_adapter"
signing_info:
  ca_fingerprint: "sha256:PLACEHOLDER"
  signed_at: "2026-01-01T00:00:00Z"
  expires_at: "2027-01-01T00:00:00Z"

resource_models:
  - resource_kind: "{your_resource_kind}"
    identity_fields: ["id"]
    label: "{Your Resource Label}"

capability_templates:
  - name: "tool.read.family.{your_name}.list"
    operation: "list"
    effect: "read"
    input_schema_ref: "schemas/list_input.schema.json"
    output_schema_ref: "schemas/list_output.schema.json"
  - name: "tool.execute.family.{your_name}.create"
    operation: "create"
    effect: "write"
    input_schema_ref: "schemas/create_input.schema.json"
    output_schema_ref: "schemas/create_output.schema.json"

event_topics:
  - "k1.capability.invoked.v1"
  - "k1.capability.completed.v1"

auth_scopes: []

safety_metadata:
  min_band: "GREEN"
  risk_class: "write"

verifier_affordances:
  - "output_schema"

freshness_guarantees:
  max_staleness_ms: 60000
```

---

## 7. Getting Help

```text
- Architecture: docs/whiteboard/back_tool_contract_whiteboard.md
- Internal onboarding: k1/fabric/docs/connector_onboarding_familyos.md
- Contract format: k1/fabric/CONTRACT.md
- Fabric integration: k1/fabric/docs/fabric_integration_guide.md
- Bridge architecture: bridge/ARCHITECTURE.md
- Example connectors: bridge/ifl/adapters/google_calendar/
- Schema validation: k1/fabric/core/contract_validator.py
- MCP transport: bridge/ifl/mcp_stdio.py
```

---

## Appendix A: Capability Naming Convention

```text
Pattern: tool.{invocation_mode}.{domain}.{service_id}.{action_name}

invocation_mode: "read" or "execute"
domain: domain prefix (e.g. "family", "enterprise", "government", "agriculture", "healthcare")
service_id: connector short name in snake_case (e.g. "calendar", "acme_calendar")
action_name: the operation verb (list, search, create, update, delete, send)

Per: k1/fabric/connectors/builder.py _cap_name() line 24.

Examples:
  tool.read.family.calendar.list         → Read calendar events
  tool.execute.family.calendar.create    → Create calendar event
  tool.execute.family.calendar.update    → Update calendar event
  tool.execute.family.calendar.delete    → Delete calendar event
```

## Appendix B: Error Codes Your Adapter Should Return

```text
Your MCP server should return these standard error shapes:

Invalid params:
  {"error": {"code": -32602, "message": "Invalid params: missing required field 'end'"}}

Auth failure:
  {"error": {"code": -32001, "message": "Authentication failed: token expired"}}

Rate limited:
  {"error": {"code": -32002, "message": "Rate limited. Retry after 30s."}}

Provider error:
  {"error": {"code": -32003, "message": "Upstream provider error: 503 Service Unavailable"}}

Timeout:
  {"error": {"code": -32004, "message": "Operation timed out after 5000ms"}}

Not found:
  {"error": {"code": -32005, "message": "Event not found: evt_12345"}}
```

## Appendix C: JSON Schema Quick Reference

```json
{
  "type": "string",
  "type": "integer", "type": "number", "type": "boolean",
  "type": "array",  "items": { ... },
  "type": "object", "properties": { ... }, "required": [...],
  "enum": ["value1", "value2"],
  "format": "date-time",    // ISO 8601
  "format": "email",
  "format": "uri",
  "minLength": 1, "maxLength": 200,
  "minimum": 0, "maximum": 100,
  "pattern": "^[a-z0-9_]+$",
  "additionalProperties": false
}
```
