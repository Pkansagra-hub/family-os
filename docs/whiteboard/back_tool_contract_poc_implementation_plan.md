# Back Tool Contract POC — Implementation Plan

**Status:** Active implementation plan.
**Source design:** [back_tool_contract_poc_design.md](back_tool_contract_poc_design.md)
**Whiteboard:** [back_tool_contract_whiteboard.md](back_tool_contract_whiteboard.md)

---

## How To Read This Plan

Each issue is self-contained. A developer must be able to read one issue and implement it without reading the whole plan. Every issue states:

- what to build
- what the code must do at the boundary (inputs, outputs, behaviors)
- what is explicitly forbidden (no mocks, no canned outputs, no if-else shortcuts)
- acceptance criteria with exact proof command
- dependencies

**Global rule for every issue in this plan:**

```text

No mocked LLM responses.
No canned capability records returned without real DB lookup.
No if-else routing that pretends to be a query.
No hardcoded "Riley = person.riley" style lookups — everything goes through the alias index.
No skipped validation ("we'll validate later").
No silent None returns — every failure is a typed error object.
No assert-passes-because-we-built-the-stub-to-pass proof.
Proof harness must report llm_mock_used=false for all live-provider tests.

```text

---

## MILESTONE 0 — Foundation

**Goal:** Proof infrastructure, SQLite store bootstrap, and shared test fixtures ready. Nothing else can be proven without this.

---

### EPIC 0-A — Proof Harness

---

#### ISSUE-001 — ProofRecordWriter and proof record schema

**What to build:**
`poc/back_tool_contract/proof.py`

A `ProofRecordWriter` class and `proof_record_template` function that every probe script uses to write structured proof records.

**Exact behavior:**

`proof_record_template(milestone_id, scenario_id, component, seam, producer, consumer, trace_id) -> dict`

Returns a partially-filled proof record dict. Must raise `ProofRecordError` (not return None) if `trace_id` is empty string or None.

`ProofRecordWriter(output_dir: str)`

Methods:
- `write_proof(record: dict) -> str` — writes JSON to `{output_dir}/{milestone_id}/{scenario_id}_{component}_{timestamp}.json`; returns the file path.
- `write_failure(record: dict, reason: str) -> str` — same but marks `all_pass=False` and sets `failure_reason`.
- `reject(record: dict, rejection_type: str, detail: str) -> None` — writes rejection record and raises `ProofRejectedError`.

**Rejection rules (must be enforced, not logged):**

```text

1. trace_id is empty or None        -> reject("missing_trace_id", ...)
2. llm_mock_used is True            -> reject("mock_llm_used", ...)
3. assertions list is empty         -> reject("empty_assertions", ...)
4. any prompt_capture_ref field contains the string "raw_catalog" -> reject("raw_catalog_in_prompt", ...)
5. any field name in the record contains "token", "secret", "credential", "oauth", "password" -> reject("secret_field_present", ...)

```text

**Shared helpers to include:**

```python

def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""

def copy_json(obj: dict) -> dict:
    """Deep copy a JSON-serializable dict."""

def redaction_check(record: dict) -> dict:
    """
    Walk all string values in record.
    Check for secret-like patterns: token, secret, credential, oauth, password, bearer, api_key.
    Return RedactionCheckResult with:
      fields_checked: int
      fields_with_leaks: list[str]  (dot-path of each offending field)
      prompt_visible_leak_count: int
      verdict: "pass" | "fail"
    """

```text

**Acceptance criteria:**

```text

- write_proof writes a valid JSON file with all required fields.
- template with empty trace_id raises ProofRecordError.
- reject with mock_llm_used raises ProofRejectedError.
- redaction_check("token": "abc123") returns verdict="fail" with fields_with_leaks=["token"].
- redaction_check on a clean record returns verdict="pass".

```text

**Proof command:**

```text

python scripts/probe_back_contract_proof_harness.py --json --record-proof

```text

**No shortcuts allowed:**

```text

- Do not skip the secret field check.
- Do not silently degrade rejection to a warning.
- Do not use try/except to swallow ProofRejectedError inside the harness itself.

```text

---

#### ISSUE-002 — ProbeReport and shared probe utilities

**What to build:**
`scripts/_probe_common.py`

`ProbeReport` class used by every probe script to collect assertion results and exit with the right code.

**Exact behavior:**

```python

class ProbeReport:
    def __init__(self, milestone_id: str, scenario_id: str = "all")
    def add_pass(self, assertion: str, detail: str = "")
    def add_fail(self, assertion: str, detail: str, evidence: dict = None)
    def add_skip(self, assertion: str, reason: str)
    def summary(self) -> dict   # returns counts and list of failures
    def exit(self)              # sys.exit(0) if no failures, sys.exit(1) if any failures
    def to_proof_record(self, component: str, seam: str, trace_id: str) -> dict

```text

**Shared fixtures to include:**

```python

def make_trace_id() -> str:
    """Generate a fresh UUID4-based trace_id. Never returns empty string."""

def load_scenario(scenario_id: str) -> dict:
    """Load scenario from poc/back_tool_contract/scenarios/scenario_corpus.json. Raises if not found."""

def load_connector_manifest(connector_id: str) -> dict:
    """Load connector manifest from poc/back_tool_contract/connectors/manifests/{connector_id}.json."""

def assert_no_secret_fields(obj: dict, path: str = "") -> list[str]:
    """
    Recursively walk obj. Return list of dot-paths where field name or value contains
    token, secret, credential, oauth, password, bearer, api_key.
    Empty list = clean.
    """

```text

**Acceptance criteria:**

```text

- ProbeReport.exit() returns 0 when all add_pass, returns 1 when any add_fail.
- to_proof_record includes all assertions in the assertions array.
- make_trace_id always returns a non-empty string.
- assert_no_secret_fields({"token": "x"}) returns ["token"].
- assert_no_secret_fields({"data": {"bearer": "y"}}) returns ["data.bearer"].

```text

**Proof command:**

```text

python scripts/probe_back_contract_proof_harness.py --json

```text

---

### EPIC 0-B — SQLite Store Bootstrap

---

#### ISSUE-003 — Global projection store schema and migration

**What to build:**
`poc/back_tool_contract/stores/global_projection_store.py`

A `GlobalProjectionStore` class that owns the `global_projection.db` SQLite database. Must use WAL mode, foreign keys ON, and strict schema.

**Tables to create (DDL in the file, run on first open):**

```sql

CREATE TABLE IF NOT EXISTS connectors (
  connector_id        TEXT PRIMARY KEY,
  label               TEXT NOT NULL,
  connector_type      TEXT NOT NULL CHECK(connector_type IN ('native_local','bridge','ifl_read','ifl_write','system')),
  provider_type       TEXT NOT NULL,
  version             TEXT NOT NULL,
  admission_verdict   TEXT NOT NULL CHECK(admission_verdict IN ('admitted','catalog_only','rejected','suspended')),
  registration_type   TEXT NOT NULL CHECK(registration_type IN ('executable','guide_only')),
  constitution_json   TEXT,
  policy_json         TEXT,
  resource_kinds_json TEXT NOT NULL,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capabilities (
  capability_name       TEXT PRIMARY KEY,
  connector_id          TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
  operation             TEXT NOT NULL,
  effect                TEXT NOT NULL CHECK(effect IN ('read','write','side_effect','system')),
  resource_kind         TEXT NOT NULL,
  description           TEXT NOT NULL,
  required_inputs_json  TEXT NOT NULL,
  optional_inputs_json  TEXT,
  output_schema_ref     TEXT,
  safety_band_min       TEXT NOT NULL CHECK(safety_band_min IN ('GREEN','AMBER','RED')),
  risk_class            TEXT NOT NULL,
  idempotency           TEXT CHECK(idempotency IN ('required','supported','none', NULL)),
  compensation_capability TEXT,
  record_type           TEXT NOT NULL CHECK(record_type IN ('executable','guide_only','catalog_ref')),
  created_at            TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts USING fts5(
  capability_name, description, resource_kind, operation,
  content='capabilities', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS resource_kinds (
  kind                TEXT PRIMARY KEY,
  label               TEXT NOT NULL,
  description         TEXT NOT NULL,
  primary_connector_id TEXT REFERENCES connectors(connector_id),
  aliases_json        TEXT,
  created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connector_constitutions (
  connector_id          TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
  operation             TEXT NOT NULL,
  preconditions_json    TEXT,
  companion_roles_json  TEXT,
  verification_json     TEXT,
  PRIMARY KEY (connector_id, operation)
);

```text

**API to expose:**

```python

class GlobalProjectionStore:
    def __init__(self, db_path: str)
    def open(self) -> None         # opens WAL connection, runs DDL
    def close(self) -> None

    # admission writes
    def upsert_connector(self, connector: dict) -> None
    def upsert_capability(self, capability: dict) -> None
    def upsert_resource_kind(self, resource_kind: dict) -> None
    def upsert_constitution(self, constitution: dict) -> None

    # queries — these must use parameterized queries, never string interpolation
    def get_connector(self, connector_id: str) -> dict | None
    def find_capabilities(self, resource_kind: str, operation: str, effect: str,
                          connector_id: str = None, safety_band: str = "GREEN",
                          record_type: str = "executable") -> list[dict]
    def fts_search_capabilities(self, query: str, limit: int = 20) -> list[dict]
    def get_constitution(self, connector_id: str, operation: str) -> dict | None
    def list_connectors(self, connector_type: str = None,
                        admission_verdict: str = "admitted") -> list[dict]
    def capability_count(self) -> int

```text

**Acceptance criteria:**

```text

- open() creates all tables and FTS index without error.
- upsert_connector + upsert_capability + capability_count returns correct count.
- find_capabilities with resource_kind=calendar_event, operation=create, effect=write
  returns only executable records for the calendar connector.
- fts_search_capabilities("dentist appointment") returns calendar-related records before
  unrelated ones.
- find_capabilities never returns guide_only records when record_type=executable.
- All queries use ? placeholders (grep the file for f" and verify zero f-string SQL).

```text

**No shortcuts allowed:**

```text

- Do not use dict as a cursor result — always map column names to dict keys.
- Do not skip WAL pragma.
- FTS index must be rebuilt when capabilities table is modified (use content= mode).

```text

---

#### ISSUE-004 — Local projection store schema and migration

**What to build:**
`poc/back_tool_contract/stores/local_projection_store.py`

A `LocalProjectionStore` class owning `local_projection.db`.

**Tables:**

```sql

CREATE TABLE IF NOT EXISTS connected_resources (
  resource_id         TEXT PRIMARY KEY,
  actor_id            TEXT NOT NULL,
  space_id            TEXT NOT NULL,
  connector_id        TEXT NOT NULL,
  resource_kind       TEXT NOT NULL,
  label               TEXT NOT NULL,
  aliases_json        TEXT,
  status              TEXT NOT NULL CHECK(status IN ('active','suspended','revoked','pending')),
  actor_permission    TEXT NOT NULL CHECK(actor_permission IN ('read_write','read_only','restricted','none')),
  last_synced_at      TEXT,
  freshness_state     TEXT NOT NULL CHECK(freshness_state IN ('fresh','stale','unknown')),
  created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS household_members (
  person_id           TEXT PRIMARY KEY,
  actor_id            TEXT NOT NULL,
  space_id            TEXT NOT NULL,
  display_name        TEXT NOT NULL,
  aliases_json        TEXT,
  role                TEXT NOT NULL CHECK(role IN ('parent','child','guardian','guest','system')),
  resource_ids_json   TEXT,
  created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alias_index (
  alias_lower         TEXT NOT NULL,
  entity_type         TEXT NOT NULL CHECK(entity_type IN ('resource','person')),
  entity_id           TEXT NOT NULL,
  actor_id            TEXT NOT NULL,
  space_id            TEXT NOT NULL,
  PRIMARY KEY (alias_lower, actor_id, entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS resource_projection_snapshots (
  snapshot_id         TEXT PRIMARY KEY,
  resource_id         TEXT NOT NULL,
  connector_id        TEXT NOT NULL,
  resource_kind       TEXT NOT NULL,
  actor_id            TEXT NOT NULL,
  query_window_json   TEXT,
  result_summary_json TEXT,
  raw_ref             TEXT,
  freshness_state     TEXT NOT NULL CHECK(freshness_state IN ('fresh','stale','unknown')),
  observed_at         TEXT NOT NULL,
  expires_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_connected_resources_actor
  ON connected_resources(actor_id, resource_kind, status);

CREATE INDEX IF NOT EXISTS idx_alias_index_lookup
  ON alias_index(alias_lower, actor_id, entity_type);

CREATE INDEX IF NOT EXISTS idx_snapshots_resource_fresh
  ON resource_projection_snapshots(resource_id, observed_at);

```text

**API:**

```python

class LocalProjectionStore:
    def open(self) -> None
    def close(self) -> None

    # writes
    def upsert_connected_resource(self, resource: dict) -> None
    def upsert_household_member(self, member: dict) -> None
    def rebuild_alias_index(self, actor_id: str, space_id: str) -> None
      # rebuilds alias_index rows for all connected_resources and household_members
      # for the given actor/space by reading aliases_json fields

    def upsert_projection_snapshot(self, snapshot: dict) -> None
    def mark_resource_stale(self, resource_id: str) -> None

    # queries
    def resolve_alias(self, alias: str, actor_id: str,
                      entity_type: str = None) -> list[dict]
      # exact match on alias_lower = lower(alias)
      # returns list of {entity_type, entity_id, alias_lower}

    def fuzzy_resolve_alias(self, alias: str, actor_id: str,
                             entity_type: str = None) -> list[dict]
      # LIKE '%{lower(alias)}%' fallback — used only when resolve_alias returns empty
      # never used as first lookup
      # returns same shape as resolve_alias

    def get_connected_resource(self, resource_id: str) -> dict | None
    def list_connected_resources(self, actor_id: str, resource_kind: str = None,
                                  status: str = "active") -> list[dict]
    def get_household_member(self, person_id: str) -> dict | None
    def get_fresh_snapshot(self, resource_id: str,
                            max_age_seconds: int = 300) -> dict | None

```text

**Acceptance criteria:**

```text

- rebuild_alias_index for actor with 2 resources and 1 person produces correct alias rows.
- resolve_alias("riley", actor_id) returns person entity if aliases_json includes "Riley".
- fuzzy_resolve_alias is only called if resolve_alias returns empty list (assert in code).
- get_fresh_snapshot returns None if snapshot older than max_age_seconds.
- mark_resource_stale updates freshness_state to 'stale'.

```text

---

### EPIC 0-C — Scenario And Connector Corpus

---

#### ISSUE-005 — Design and write all 100 request scenarios

**What to build:**
`poc/back_tool_contract/scenarios/scenario_corpus.json`
`poc/back_tool_contract/scenarios/scenario_schema.json`
`poc/back_tool_contract/scenarios/scenario_index.json`

**Each scenario must be a complete JSON record. No placeholders, no TODO fields.**

Required fields per scenario:

```json

{
  "scenario_id": "S001",
  "label": "...",
  "tier": "tier1 | tier2 | tier3",
  "complexity": "LOW | MEDIUM | HIGH",
  "user_phrase": "exact user natural language request",
  "actor_role": "parent | child",
  "safety_band": "GREEN | AMBER | RED",
  "expected_resource_kinds": ["calendar_event"],
  "expected_connectors": ["calendar"],
  "expected_operations": ["list_events", "create_event"],
  "expected_prerequisite_reads": ["list_events"],
  "expected_writes": ["create_event"],
  "expected_verification": "read_after_write | output_schema | none",
  "expected_hil": false,
  "expected_disambiguation": false,
  "expected_tier3_promotion": false,
  "expected_resolution_verdict": "can_execute_with_prerequisite_read",
  "expected_submit_status": "completed | partial | needs_hil | cannot_execute | failed",
  "expected_allowed_next_actions_contain": ["invoke bind for list_events"],
  "expected_forbidden_next_actions_contain": ["invoke create_event before list_events"],
  "person_refs_in_phrase": ["Riley"],
  "resource_refs_in_phrase": ["family calendar"],
  "time_refs_in_phrase": ["tomorrow at 5pm"],
  "param_normalization_required": ["duration_minutes -> end"],
  "negative_assertions": [
    {
      "text": "resolver must not return can_execute without prerequisite read",
      "assertion_type": "resolver_not_can_execute_before_prerequisite",
      "params": {"capability": "create_event"}
    },
    {
      "text": "create_event must not be in allowed_next_actions at Phase 1",
      "assertion_type": "capability_not_in_allowed_at_phase",
      "params": {"capability": "create_event", "phase": "connector_summary"}
    }
  ],
  "notes": "..."
}

```text

**Scenario distribution (must be exactly this):**

```text

S001-S015  Tier 1 conversational, no execution expected
S016-S035  Tier 2 single-connector reads (calendar list, task list, reminder list, notes search)
S036-S060  Tier 2 single-connector writes (calendar create, task create, reminder create, notes create)
S061-S075  Tier 2 prerequisite read + write (conflict check before create, get before update)
S076-S085  Tier 2 disambiguation and HIL (ambiguous person, ambiguous time, missing required param)
S086-S093  Tier 3 multi-connector (calendar + contacts, calendar + reminders)
S094-S098  Tier 3 cross-resource with companion participants
S099       Budget exhaustion mid-loop
S100       Duplicate idempotency key after success (no-op expected)

```text

**Negative assertion rule:**
Every scenario must have at least one `negative_assertions` entry. A scenario without a negative assertion is incomplete. Each negative assertion is a typed object. The human text is explanatory only; the proof harness evaluates `assertion_type` and `params`.

**Required `NegativeAssertionType` values:**

```text

resolver_not_can_execute_before_prerequisite
capability_not_in_allowed_at_phase
capability_never_invoked
submit_result_not_completed_without_verification
no_hallucinated_resource_or_capability_id
prompt_pack_no_schema_at_phase
prompt_pack_no_raw_catalog_or_secret
hil_required_before_needs_hil_submit

```text

The negative assertion evaluator must return `pass`, `fail`, or `skip`. A `skip` requires a machine-readable `skip_reason`; it must never be counted as pass.

**Acceptance criteria:**

```text

- scenario_corpus.json validates against scenario_schema.json with zero errors.
- 100 entries, each with unique scenario_id.
- Every scenario has at least one negative_assertion.
- Every negative_assertion has `text`, `assertion_type`, and `params`.
- Every `assertion_type` is one of the required `NegativeAssertionType` values.
- scenario_index.json correctly groups by tier, connector, expected_verdict.
- No scenario has user_phrase = "" or label = "TODO".
- Every expected_writes scenario has expected_verification != null.

```text

**Proof command:**

```text

python scripts/probe_back_task_envelope.py --validate-corpus --json

```text

---

#### ISSUE-006 — Design and write all 40 connector manifests

**What to build:**
`poc/back_tool_contract/connectors/manifests/{connector_id}.json` — 40 files
`poc/back_tool_contract/connectors/index/connector_index.json`
`poc/back_tool_contract/connectors/index/capability_index.json`

**Connector list:**

```text

Native local (10):
  calendar, tasks, reminders, notes, contacts
  chores, habits, budgets, shopping, documents

Bridge-connected (10):
  google_calendar_read, google_tasks, todoist, notion,
  apple_reminders, slack_dm, email_send, weather,
  news_digest, location_context

IFL read-only (10):
  school_calendar_read, sports_schedule_read,
  doctor_appointment_read, pharmacy_refill_status,
  bank_balance_read, package_tracking,
  flight_status, local_events_read,
  transit_schedule_read, air_quality_read

IFL write-capable (5):
  restaurant_reservation_create, appointment_book,
  ticket_purchase, rideshare_book, food_order

System/platform (5):
  family_broadcast, alert_send, reminder_fire,
  audit_log_write, notification_push

```text

**Each manifest must include (no placeholder fields):**

```json

{
  "connector_id": "calendar",
  "connector_type": "native_local",
  "provider_type": "LOCAL",
  "label": "...",
  "description": "...",
  "version": "1.0.0",
  "provider_id": "...",
  "resource_kinds": ["calendar_event", "calendar"],
  "actor_scope": ["parent", "child_read_own", "system"],
  "constitution": {
    "preconditions": {
      "create_event": ["list_events for target time window"]
    },
    "companion_resource_roles": {},
    "verification": {
      "create_event": "read_after_write via get_event"
    }
  },
  "capabilities": [
    {
      "capability_name": "tool.read.calendar.list_events",
      "operation": "list",
      "effect": "read",
      "resource_kind": "calendar_event",
      "description": "...",
      "required_inputs": ["calendar_id", "time_min", "time_max"],
      "optional_inputs": [...],
      "output_schema_ref": "calendar_event_list.schema.json",
      "safety_band_min": "GREEN",
      "risk_class": "read_only",
      "idempotency": null,
      "compensation_capability": null
    }
  ],
  "policy_declarations": {
    "write_requires_actor_role": ["parent", "system"],
    "read_allowed_roles": ["parent", "child_read_own"],
    "hil_triggers": [],
    "protected_resources": []
  },
  "registration_type": "executable",
  "admission_verdict": "admitted"
}

```text

**IFL guide-only manifests (some IFL connectors must be guide_only to test the admission path):**

```text

weather and news_digest must have registration_type="guide_only" and admission_verdict="catalog_only".
This tests that the admission service rejects these as executable and they never appear in bindings.

```text

**Acceptance criteria:**

```text

- 40 manifest files, each validating against connector manifest schema.
- capability_index.json lists every capability_name with its connector_id, resource_kind, operation, effect.
- Native local connectors have at least one read capability and one write capability.
- All write capabilities have idempotency = "required" or "supported".
- Write capabilities have compensation_capability set or explicitly null with a note.
- guide_only manifests (weather, news_digest) have no write capabilities.

```text

---

## MILESTONE 1 — Global And Local Projection

**Goal:** Both stores are populated from real manifests and real fixture data. Resolver resource queries return real answers. No hardcoded lookups.

---

### EPIC 1-A — Global Projection Population

---

#### ISSUE-007 — ManifestAdmissionService

**What to build:**
`poc/back_tool_contract/manifest_registration.py`

A `ManifestAdmissionService` that reads connector manifest JSON files, validates them, classifies them, and writes them into `GlobalProjectionStore`.

**Exact behavior:**

```python

class ManifestAdmissionService:
    def __init__(self, store: GlobalProjectionStore)

    def admit_manifest(self, manifest: dict) -> ManifestAdmissionRecord:
        """
        1. Validate manifest against connector manifest schema (jsonschema).
           Raise ManifestSchemaError on invalid.
        2. Check registration_type field.
           - "executable" -> admission_verdict = "admitted"
           - "guide_only" -> admission_verdict = "catalog_only"
           - Neither -> admission_verdict = "rejected", record reason
        3. For admitted manifests:
           - Write connector row via store.upsert_connector
           - For each capability in manifest.capabilities:
               - set record_type = "executable" if connector is admitted
               - set record_type = "guide_only" if connector is catalog_only
               - write capability row via store.upsert_capability
           - Write resource_kinds rows
           - Write constitution rows
        4. For catalog_only manifests:
           - Write connector row with admission_verdict = catalog_only
           - Write capability rows with record_type = guide_only
           - DO NOT write executable capabilities
        5. Return ManifestAdmissionRecord with:
             manifest_id, connector_id, admission_verdict, record_type,
             capabilities_admitted_count, capabilities_rejected_count,
             reason (if rejected), admitted_at
        """

    def admit_all_from_directory(self, directory: str) -> list[ManifestAdmissionRecord]:
        """Load and admit all .json files in directory."""

```text

**Acceptance criteria:**

```text

- Admitting calendar.json produces admitted record with correct capability count.
- Admitting weather.json produces catalog_only record.
- find_capabilities(record_type="executable") never returns weather capabilities.
- Admitting malformed JSON raises ManifestSchemaError.
- Re-admitting same connector_id upserts (no duplicate error).

```text

**Proof command:**

```text

python scripts/probe_manifest_translator.py --json --record-proof

```text

---

#### ISSUE-008 — Bulk manifest load and 100k scale proof

**What to build:**
`poc/back_tool_contract/stores/scale_loader.py`

A script + helper that loads all 40 manifests, then generates synthetic variants to reach 100,000 capability rows, and proves indexed lookup stays fast.

**Synthetic generation rule:**
For each of the 40 real connectors, generate 2,500 variant capabilities:
- vary the `resource_kind` suffix
- vary the `operation` prefix
- keep `record_type = "executable"` for admitted connectors

These are not real connectors; they exist only to prove the SQLite indexes hold at scale.

**Synthetic data isolation rule:**
Synthetic rows must have `synthetic = true` in their stored contract JSON and a separate indexed `synthetic` column. Production authority query paths must default to `synthetic = 0`; synthetic rows may only be returned when a probe explicitly passes `include_synthetic=True`. FTS/BM25 catalog probes may include synthetic rows only in scale-specific measurements, never in resolver authority decisions.

**Performance assertions:**

```python

def assert_query_performance(store: GlobalProjectionStore):
    """
    Assert that after 100,000 capability rows:
    1. find_capabilities(resource_kind=X, operation=Y, effect=Z) runs in < 10ms (median over 100 calls).
    2. fts_search_capabilities(query) runs in < 50ms (median over 100 calls).
    3. capability_count() returns >= 100_000.
    4. Real authority lookups with include_synthetic=False never return synthetic rows.
    """

```text

**Acceptance criteria:**

```text

- capability_count() >= 100,000 after load.
- Indexed find_capabilities median < 10ms.
- FTS search median < 50ms.
- Real connector manifests are not mixed with synthetic rows (synthetic rows have a "synthetic": true field).
- Resolver authority lookup APIs default to excluding synthetic rows.

```text

**Proof command:**

```text

python scripts/probe_production_back_runtime.py --json --record-proof

```text

---

### EPIC 1-B — Local Projection Population

---

#### ISSUE-009 — Household fixture loader

**What to build:**
`poc/back_tool_contract/fixtures/household_fixture.py`

A `HouseholdFixtureLoader` that populates `LocalProjectionStore` with realistic household data for all 100 scenarios.

**Fixture data to include:**

```python

HOUSEHOLD_FIXTURE = {
  "actor_id": "actor_parent_001",
  "space_id": "space_family_001",
  "members": [
    {
      "person_id": "person.riley",
      "display_name": "Riley",
      "aliases": ["Riley", "riley", "RK", "Riley K"],
      "role": "child",
      "resource_ids": {"calendar_id": "calendar.riley.primary"}
    },
    {
      "person_id": "person.jordan",
      "display_name": "Jordan",
      "aliases": ["Jordan", "jordan", "JK"],
      "role": "child",
      "resource_ids": {"calendar_id": "calendar.jordan.primary"}
    },
    {
      "person_id": "person.parent_a",
      "display_name": "Alex",
      "aliases": ["Alex", "alex", "Mum", "mum"],
      "role": "parent",
      "resource_ids": {"calendar_id": "calendar.alex.primary"}
    }
  ],
  "connected_resources": [
    {
      "resource_id": "calendar.family.primary",
      "connector_id": "calendar",
      "resource_kind": "calendar",
      "label": "Family Calendar",
      "aliases": ["family calendar", "main calendar", "family cal"],
      "status": "active",
      "actor_permission": "read_write",
      "freshness_state": "fresh"
    },
    {
      "resource_id": "calendar.riley.primary",
      "connector_id": "calendar",
      "resource_kind": "calendar",
      "label": "Riley's Calendar",
      "aliases": ["riley calendar", "riley's calendar"],
      "status": "active",
      "actor_permission": "read_write",
      "freshness_state": "fresh"
    },
    {
      "resource_id": "tasks.family.primary",
      "connector_id": "tasks",
      "resource_kind": "task_list",
      "label": "Family Tasks",
      "aliases": ["family tasks", "tasks", "todo"],
      "status": "active",
      "actor_permission": "read_write",
      "freshness_state": "fresh"
    }
    // ... continue for all connectors scenarios reference
  ]
}

```text

**Additional fixture variants for disambiguation scenarios:**

```python

AMBIGUOUS_FIXTURE = {
  # Two people named Riley (for S076-S078 disambiguation scenarios)
  "members": [
    { "person_id": "person.riley_k", "display_name": "Riley K",
      "aliases": ["Riley", "Riley K"], "role": "child" },
    { "person_id": "person.riley_t", "display_name": "Riley T",
      "aliases": ["Riley", "Riley T"], "role": "guest" }
  ]
}

```text

**Acceptance criteria:**

```text

- After load, resolve_alias("riley", actor_id) returns person.riley in standard fixture.
- After load with ambiguous fixture, resolve_alias("riley", actor_id) returns two entries.
- After load, resolve_alias("family calendar", actor_id) returns resource.calendar.family.primary.
- All 100 scenarios' person_refs_in_phrase and resource_refs_in_phrase resolve correctly.

```text

---

#### ISSUE-010 — ProjectionDelta ingestion

**What to build:**
`poc/back_tool_contract/projection_delta.py`

`ProjectionDeltaIngester` that takes an `InvocationObservation` from a read call and updates `resource_projection_snapshots`.

**Exact behavior:**

```python

class ProjectionDeltaIngester:
    def __init__(self, store: LocalProjectionStore)

    def ingest(self, observation: dict, query_window: dict = None) -> ProjectionDeltaRecord:
        """
        1. Extract resource_id, connector_id, resource_kind from observation.
        2. Extract result summary (item count, key fields) from observation.structured_result.
        3. Build snapshot_id = hash(resource_id + observed_at + query_window).
        4. Compute expires_at = observed_at + DEFAULT_TTL_SECONDS (default: 300).
        5. Write or update resource_projection_snapshots via store.upsert_projection_snapshot.
        6. Update connected_resources.freshness_state = 'fresh' for the resource.
        7. Return ProjectionDeltaRecord with:
             delta_id, resource_id, snapshot_id, items_observed, observed_at,
             expires_at, prior_freshness_state, new_freshness_state
        """

    def is_fresh(self, resource_id: str, max_age_seconds: int = 300) -> bool:
        """Return True if a fresh snapshot exists within max_age_seconds."""

```text

**Acceptance criteria:**

```text

- ingest(list_events observation) creates a snapshot with correct resource_id and expires_at.
- is_fresh returns True immediately after ingest.
- is_fresh returns False after TTL expires (manipulate observed_at in test).
- ingest updates freshness_state from stale to fresh.
- ingest on a different query window creates a separate snapshot, does not invalidate prior.

```text

**Proof command:**

```text

python scripts/probe_projection_delta.py --json --record-proof

```text

---

## MILESTONE 2 — Request Authority Intake

**Goal:** Back can receive a BackTaskEnvelope, build a RequestFrame from it, and call resolve_situation. The resolver returns a valid ResolutionEnvelope. All 100 scenarios produce a ResolutionEnvelope.

---

### EPIC 2-A — BackTaskEnvelope and RequestFrame

---

#### ISSUE-011 — BackTaskEnvelope dataclass and FSM parser

**What to build:**
`poc/back_tool_contract/back_task_envelope.py`

**Types:**

```python

@dataclass
class BackTaskBudget:
    max_iterations: int
    max_fabric_calls: int
    max_prompt_tokens: int

@dataclass
class BackTaskEnvelope:
    envelope_id: str
    task_id: str
    trace_id: str
    session_id: str
    actor_id: str
    space_id: str
    tier: str           # "LOW" | "MEDIUM" | "HIGH"
    safety_band: str    # "GREEN" | "AMBER" | "RED"
    task_dispatch: dict # raw TaskDispatch payload
    budget: BackTaskBudget
    session_state_ref: str | None
    grounding_envelope_id: str | None
    temporal_anchor_id: str | None
    spatial_context_id: str | None
    submitted_at: str

def parse_back_task_envelope(payload: dict) -> BackTaskEnvelope:
    """
    Parse from FSM mailbox payload dict.
    Must raise BackTaskEnvelopeError (with field name) for:
      - missing task_id
      - missing trace_id
      - invalid tier (not LOW/MEDIUM/HIGH)
      - invalid safety_band (not GREEN/AMBER/RED)
      - missing task_dispatch
    Must generate envelope_id if absent (UUID4).
    Must generate trace_id if absent (UUID4) — log warning but do not fail.
    """

```text

**No shortcuts:**

```text

- Do not return a BackTaskEnvelope with tier=None when tier is missing — raise.
- Do not silently default safety_band to GREEN if it is absent — raise.
- Do not use hasattr checks with silent defaults for required fields.

```text

**Acceptance criteria:**

```text

- Valid payload produces BackTaskEnvelope with correct fields.
- Missing task_id raises BackTaskEnvelopeError("task_id").
- Unknown tier value raises BackTaskEnvelopeError("tier").
- envelope_id is generated when absent.
- All 100 scenario TaskDispatch payloads parse without error.

```text

---

#### ISSUE-012 — RequestFrameBuilder

**What to build:**
`poc/back_tool_contract/request_frame_builder.py`

**Types:**

```python

@dataclass
class PersonRef:
    raw: str
    confidence: str    # "high" | "medium" | "low"
    needs_resolution: bool

@dataclass
class ResourceRef:
    raw: str
    resource_kind_hint: str | None
    confidence: str
    needs_resolution: bool

@dataclass
class TimeWindowHint:
    raw_phrase: str
    resolved_start: str | None    # ISO 8601 or None
    resolved_end: str | None
    confidence: str               # "high" | "medium" | "low" | "unresolvable"

@dataclass
class RequestFrameIntent:
    intent_id: str
    action: str
    domain: str | None
    operation_hint: str    # "create" | "list" | "read" | "update" | "delete" | "compute" | "fire"
    resource_kind_hint: str | None
    subject_hint: str | None
    params: dict

@dataclass
class RequestFrame:
    request_id: str
    task_id: str
    trace_id: str
    actor_id: str
    space_id: str
    intents: list[RequestFrameIntent]
    time_window_hint: TimeWindowHint | None
    person_refs: list[PersonRef]
    resource_refs: list[ResourceRef]
    safety_context: dict
    target_tier: str
    resolution_mode: str    # "execution" | "catalog" | "diagnostic"
    created_at: str

class RequestFrameBuilder:
    def build(self, envelope: BackTaskEnvelope) -> RequestFrame:
        """
        1. For each intent in envelope.task_dispatch.intents:
           a. Derive operation_hint from action keyword:
              create/add/schedule/book  -> "create"
              list/find/search/show     -> "list"
              get/fetch/read            -> "read"
              update/edit/change/modify -> "update"
              delete/remove/cancel      -> "delete"
           b. Derive resource_kind_hint from domain field and action keywords:
              calendar/event/appointment -> "calendar_event"
              task/todo/chore            -> "task"
              reminder/alert             -> "reminder"
              note/notes                 -> "note"
              contact/person             -> "contact"
           c. Extract person_hint from params (person_hint, participant, attendee, for_person)
           d. Extract resource_hint from params (calendar_hint, list_hint, etc)
           e. Extract time hints from params (date, time, date_hint, time_hint, duration_minutes)
        2. Resolve relative time refs:
           "tomorrow" -> date arithmetic from utc_now_iso()
           "5pm"      -> combine with resolved date, apply actor timezone from space context if available
           If timezone unknown, mark confidence="medium" and note in time_window_hint.
        3. Set resolution_mode = "execution" always (not catalog, not diagnostic).
        4. Set target_tier from envelope.tier.
        """

```text

**Acceptance criteria:**

```text

- "Add Riley's dentist appointment tomorrow at 5pm for 45 minutes" produces:
    operation_hint = "create"
    resource_kind_hint = "calendar_event"
    person_refs = [PersonRef("Riley", "high", True)]
    resource_refs = [ResourceRef("family calendar", "calendar", ...)]
    time_window_hint.confidence != "unresolvable"
- All 100 scenario user_phrases produce non-empty RequestFrame with at least one intent.
- operation_hint is never null (default to "compute" if unrecognized).
- resolution_mode is always "execution".

```text

**Proof command:**

```text

python scripts/probe_back_task_envelope.py --json --record-proof

```text

---

### EPIC 2-B — Resolve Situation Service

---

#### ISSUE-013 — ResolveSituationService core

**What to build:**
`poc/back_tool_contract/resolve_situation.py`

`ResolveSituationService` that orchestrates CC-2, CC-3, CC-4 and returns a `ResolutionEnvelope`.

**Types:**

```python

@dataclass
class ResolveSituationRequest:
    request_frame: RequestFrame
    actor_scope: dict
    safety_context: dict
    resolution_mode: str
    target_tier: str
    disclosure_phase: str     # "connector_summary" | "tool_name_selection" | "schema_binding" | "execution"
    freshness_policy: str     # "strict" | "relaxed"
    prompt_budget: int        # max tokens for PromptPack
  completed_prerequisite_bindings: list[str]
    previous_resolution_id: str | None

@dataclass
class ResolutionEnvelope:
    resolution_id: str
    request_id: str
    request_frame: RequestFrame
    candidate_universe: CandidateUniverse
    prompt_pack: PromptPack
    policy_bundle_ref: str
    binding_bundle_ref: str
    completeness: str         # "complete" | "partial" | "unknown"
    freshness: str            # "fresh" | "stale" | "unknown"
    verdict: str
    allowed_next_actions: list[str]
    diagnostics: list[dict]
    created_at: str
    expires_at: str

class ResolveSituationService:
    def __init__(self,
                 resource_resolver: ResolveResourcesService,
                 policy_selector: PolicySelectorService,
                 capability_binder: CapabilityBinderService,
                 prompt_pack_builder: PromptPackBuilder,
                 global_store: GlobalProjectionStore,
                 local_store: LocalProjectionStore)

    def resolve(self, request: ResolveSituationRequest) -> ResolutionEnvelope:
        """
        Step 1: Call resource_resolver.resolve(ResolveResourcesRequest from frame)
        Step 2: If ResourceUniverse.completeness == "unknown":
                  return ResolutionEnvelope(verdict="incomplete_world_projection")
                If ResourceUniverse.unresolved has person refs:
                  if exactly one match possible: return needs_disambiguation
                  if zero matches: return missing_capability or cannot_execute
        Step 3: Call policy_selector.select(PolicySelectionRequest from universe)
        Step 4: If policy verdict == "deny":
                  return ResolutionEnvelope(verdict="blocked_by_policy")
        Step 5: Check freshness: if any write operation and freshness_state=="stale":
                  return ResolutionEnvelope(verdict="stale_projection")
        Step 6: Call capability_binder.bind(BindingRequest from universe + policy)
        Step 7: Build CandidateUniverse from universe + policy + bindings
        Step 8: Determine allowed_next_actions from constitution preconditions:
                  If preconditions exist for intended write: allowed = [prerequisite reads only]
            Once prerequisite reads are satisfied (caller passes their binding IDs in
            completed_prerequisite_bindings): allowed = [write binding]
        Step 9: Build PromptPack at requested disclosure_phase
        Step 10: Return ResolutionEnvelope
        """

```text

      **Prerequisite completion state contract:**

      ```text

      ResolveSituationService is stateless. It must never infer prerequisite completion from process memory. The Back loop owns prerequisite progress in ReactLoopState and passes `completed_prerequisite_bindings` into every ResolveSituationRequest. Resolver output must include enough binding metadata for the caller to know which prerequisite binding completed and which primary write binding becomes legal after re-resolution.

      ```text

**Verdict taxonomy (all must be handled):**

```text

can_execute                    all clear, no prerequisites
can_execute_with_gate          prerequisite reads required first
needs_disambiguation           ambiguous person/resource reference
missing_required_params        incomplete RequestFrame params
missing_capability             no admitted capability for operation+resource_kind
blocked_by_policy              policy hard deny
stale_projection               write blocked due to stale local projection
incomplete_world_projection    cannot confirm resource scope
promote_to_tier3               cross-resource task, escalate
cannot_execute                 budget or safety block

```text

**Acceptance criteria:**

```text

- All 100 scenarios produce a ResolutionEnvelope with correct verdict (compare to scenario.expected_resolution_verdict).
- S076-S085 (disambiguation) produce needs_disambiguation or missing_required_params.
- Scenarios with expected_prerequisite_reads produce can_execute_with_gate.
- Re-resolution with completed_prerequisite_bindings for required reads permits the matching write binding in allowed_next_actions.
- Stale fixture resource produces stale_projection verdict.
- guide_only connector produces missing_capability verdict (not can_execute).

```text

**Proof command:**

```text

python scripts/probe_resolve_situation.py --json --record-proof

```text

---

## MILESTONE 3 — Resolver Internal Components

**Goal:** CC-2 resource resolution, CC-3 policy selection, CC-4 capability binding each work independently and together. Model-tests for prompt surface pass.

---

### EPIC 3-A — Resource Resolution

---

#### ISSUE-014 — ResolveResourcesService

**What to build:**
`poc/back_tool_contract/resource_projection.py`

**Types:**

```python

@dataclass
class ResourceCandidate:
    resource_id: str
    label: str
    resource_kind: str
    connector_id: str
    actor_permission: str
    freshness_state: str
    aliases: list[str]

@dataclass
class PersonCandidate:
    person_id: str
    label: str
    role: str
    linked_resource_ids: dict    # {"calendar_id": "calendar.riley.primary"}
    resolved: bool

@dataclass
class UnresolvedRef:
    raw: str
    entity_type: str    # "person" | "resource"
    reason: str         # "not_found" | "ambiguous" | "revoked" | "permission_denied"
    candidates: list[dict]    # populated if ambiguous

@dataclass
class ScopeProof:
    scope_proof_id: str
    actor_id: str
    space_id: str
    projection_sources: list[dict]    # each: source, entity_ids_considered, freshness, queried_at
    omissions: list[dict]
    exclusions: list[dict]
    completeness: str

@dataclass
class ResourceUniverse:
    universe_id: str
    resource_candidates: list[ResourceCandidate]
    person_candidates: list[PersonCandidate]
    unresolved: list[UnresolvedRef]
    scope_proof: ScopeProof
    completeness: str    # "complete" | "partial" | "unknown"
    freshness: str

class ResolveResourcesService:
    def resolve(self, frame: RequestFrame, actor_id: str,
                space_id: str) -> ResourceUniverse:
        """
        For each person_ref in frame.person_refs:
          1. local_store.resolve_alias(ref.raw, actor_id, entity_type="person")
             If 0 results: try fuzzy_resolve_alias
             If still 0: add UnresolvedRef(reason="not_found")
             If 1 result: resolve to PersonCandidate
             If 2+ results: add UnresolvedRef(reason="ambiguous", candidates=[...])
             Never guess — if ambiguous, do not pick one.

        For each resource_ref in frame.resource_refs:
          1. Same alias resolution pattern.
          2. After resolving resource_id:
             - verify connected_resource.status == "active"
             - verify actor_permission allows the operation
             - check freshness_state
          3. Verify connector.admission_verdict == "admitted" in global_store.
             If not: add to omissions with reason="connector_not_admitted".

        Build ScopeProof listing every entity considered.
        Determine completeness:
          - If any write operation and any unresolved ref: "unknown" (blocks write)
          - If disambiguation refs exist: "partial"
          - If all resolved and admitted: "complete"
        """

```text

**Acceptance criteria:**

```text

- "Riley" in standard fixture resolves to PersonCandidate(person_id="person.riley").
- "Riley" in ambiguous fixture returns UnresolvedRef(reason="ambiguous", candidates=[2 options]).
- "family calendar" resolves to ResourceCandidate(resource_id="calendar.family.primary").
- Guide-only connector resource returns omission with reason="connector_not_admitted".
- ScopeProof.projection_sources lists every queried table/source.

```text

**Proof command:**

```text

python scripts/probe_resource_projection.py --json --record-proof

```text

---

### EPIC 3-B — Policy Selection

---

#### ISSUE-015 — PolicySelectorService

**What to build:**
`poc/back_tool_contract/policy_selector.py`

**Types:**

```python

@dataclass
class PolicyGate:
    gate_id: str
    gate_type: str    # "precondition" | "hil_trigger" | "safety_band" | "role_check" | "protected_read"
    description: str
    condition: dict
    action_required: str    # "run_read_first" | "ask_hil" | "deny" | "allow_with_evidence"

@dataclass
class PolicyBundle:
    policy_id: str
    connector_ids: list[str]
    operations: list[str]
    actor_role: str
    safety_band: str
    roles_allowed: dict            # {operation: [allowed_roles]}
    gates: list[PolicyGate]
    hil_triggers: list[dict]
    protected_read_policy: dict | None
    guide_refs: list[str]
    verifier_requirements: dict    # {operation: verification_method}
    policy_verdict: str            # "allow" | "deny" | "allow_with_gate" | "needs_hil"
    deny_reason: str | None
    safety_mapping_evidence: dict | None

class PolicySelectorService:
    def __init__(self, global_store: GlobalProjectionStore)

    def select(self, resource_universe: ResourceUniverse,
               operations: list[str], actor_role: str,
               safety_band: str) -> PolicyBundle:
        """
        For each connector in resource_universe.resource_candidates:
          1. Load connector.policy_json from global_store.get_connector.
          2. Check roles_allowed: if actor_role not in policy.write_requires_actor_role for writes:
                policy_verdict = "deny", deny_reason = "role_not_allowed"
          3. Check safety_band_min for each operation:
                If safety_band < capability.safety_band_min:
                  Build SafetyMappingEvidence and set policy_verdict = "deny"
                  (GREEN < AMBER < RED ordering)
          4. Check hil_triggers from constitution:
                If any trigger condition matches: add to hil_triggers
          5. Check preconditions from constitution:
                If create operation has preconditions: add precondition gates
          6. Build verifier_requirements from constitution.verification.

        If any deny: return PolicyBundle(policy_verdict="deny").
        If hil_triggers: return PolicyBundle(policy_verdict="needs_hil").
        If gates exist: return PolicyBundle(policy_verdict="allow_with_gate").
        Else: PolicyBundle(policy_verdict="allow").
        """

```text

**SafetyMappingEvidence must be built (not just a string):**

```python

@dataclass
class SafetyMappingEvidence:
    evidence_id: str
    operation: str
    required_band: str
    actual_band: str
    connector_id: str
    capability_name: str
    mapping_result: str    # "pass" | "deny" | "degraded"
    hard_block_reason: str | None

```text

**Acceptance criteria:**

```text

- Parent creating calendar event produces policy_verdict="allow_with_gate" (precondition gate).
- Child creating calendar event produces policy_verdict="deny" (role not allowed).
- GREEN task with GREEN-minimum create returns allow_with_gate.
- GREEN task with AMBER-minimum capability returns SafetyMappingEvidence + deny.
- delete_event with participants>1 produces needs_hil (from hil_triggers).
- verifier_requirements contains "create_event": "read_after_write" for calendar connector.

```text

**Proof command:**

```text

python scripts/probe_policy_selector.py --json --record-proof

```text

---

### EPIC 3-C — Capability Binding

---

#### ISSUE-016 — CapabilityBinderService

**What to build:**
`poc/back_tool_contract/capability_binder.py`

**Types:**

```python

@dataclass
class CapabilityBinding:
    binding_id: str        # deterministic hash(connector_id+capability_name+resource_id+actor_id+session_id)
    role: str              # "prerequisite_read" | "primary_write" | "verification_read" | "companion_read"
    capability_name: str
    resource_id: str
    connector_id: str
    contract_ref: str      # references capability row in GlobalProjectionStore
    input_schema_ref: str | None
    output_schema_ref: str | None
    effect_summary: str
    safety_requirement: str
    authority_verdict: str    # "bound" | "stale" | "denied"
    verifier_ref: str | None
    guide_refs: list[str]
    freshness_state: str
    limitations: list[str]
    created_at: str
    expires_at: str

@dataclass
class UnboundRole:
    operation: str
    resource_kind: str
    reason: str    # "missing_capability" | "missing_connector" | "policy_block" | "stale_projection" | "guide_only_only"
    detail: str

@dataclass
class BindingBundle:
    binding_bundle_id: str
    bindings: list[CapabilityBinding]
    unbound_roles: list[UnboundRole]
    tool_name_cards: list[dict]       # names + one-line descriptions, NO schemas
    selected_schema_cards: list[dict] # populated only at schema_binding phase
    guide_refs: list[str]
    verifier_links: list[dict]
    binding_diagnostics: list[str]
    disclosure_phase: str

class CapabilityBinderService:
    def __init__(self, global_store: GlobalProjectionStore,
                 local_store: LocalProjectionStore)

    def bind(self, resource_universe: ResourceUniverse,
             policy_bundle: PolicyBundle,
             intended_operations: list[str],
             actor_id: str, session_id: str,
             disclosure_phase: str) -> BindingBundle:
        """
        For each intended operation:
          1. Determine resource_kind from operation hint + ResourceUniverse.
          2. Determine connector_id from matched ResourceCandidate.connector_id.
          3. Execute EXACT registry lookup in global_store:
               find_capabilities(resource_kind, operation, effect, connector_id, record_type="executable")
             This is the ONLY lookup. No top-K semantic ranking as authority.
          4. If 0 results: add UnboundRole(reason="missing_capability").
          5. If results: pick by safety_band_min <= actor safety_band.
          6. Verify policy_bundle allows this role.
          7. Check freshness of resource from ResourceUniverse.
             If stale and operation is write: add UnboundRole(reason="stale_projection").
          8. Build CapabilityBinding with deterministic binding_id.
          9. Assign role:
               prerequisite read operations -> "prerequisite_read"
               primary write operation -> "primary_write"
               verification readback -> "verification_read"
          10. Set expires_at = now + 300 seconds.

        Build tool_name_cards: [{"name": cap.capability_name, "description": cap.description}]
        Do NOT include schemas in tool_name_cards at Phase 1.
        At schema_binding phase: populate selected_schema_cards with full schemas
          only for bindings that have been committed by the model.
        """

    def refresh_binding(self, binding_id: str) -> CapabilityBinding:
        """Re-derive a binding from scratch. Never use a cached stale binding as authority."""

```text

**binding_id generation:**

```python

import hashlib

def make_binding_id(connector_id: str, capability_name: str,
                    resource_id: str, actor_id: str, session_id: str) -> str:
    raw = f"{connector_id}:{capability_name}:{resource_id}:{actor_id}:{session_id}"
    return "bind_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

```text

**Acceptance criteria:**

```text

- create_event intent produces CapabilityBinding with role="primary_write" and
  a separate prerequisite binding with role="prerequisite_read".
- guide_only connector produces UnboundRole(reason="missing_capability").
- Stale resource + write operation produces UnboundRole(reason="stale_projection").
- Phase 1 BindingBundle.tool_name_cards contains names only, no schemas.
- Phase 3 BindingBundle.selected_schema_cards populated only for committed bindings.
- Two bindings with same inputs produce identical binding_id (deterministic hash).

```text

**Proof command:**

```text

python scripts/probe_binder.py --json --record-proof

```text

---

## MILESTONE 4 — PromptPack And Back Prompt Redesign

**Goal:** The Back LLM receives only what it needs, in the right phase, with zero secret leaks. The Back system prompt is designed to work with the new authority contract.

---

### EPIC 4-A — PromptPack Builder

---

#### ISSUE-017 — PromptPackBuilder

**What to build:**
`poc/back_tool_contract/prompt_injection.py`

**Types:**

```python

@dataclass
class ConstitutionCard:
    connector_id: str
    label: str
    preconditions: list[str]          # plain-English sentences
    companion_resource_roles: dict
    verification_requirement: str     # "read_after_write" | "output_schema" | "none"

@dataclass
class ToolNameCard:
    capability_name: str
    description: str
    role: str    # "prerequisite_read" | "primary_write" | etc

@dataclass
class PolicyCard:
    connector_id: str
    what_is_required: str
    what_triggers_hil: list[str]
    what_is_denied: list[str]

@dataclass
class GuideCard:
    guide_id: str
    title: str
    content: str        # plain-English procedural guidance
    relevance: str      # why this guide is relevant to the current request

@dataclass
class SchemaCard:
    capability_name: str
    binding_id: str
    input_schema: dict    # full JSON Schema object for required inputs only
    required_fields: list[str]
    optional_fields: list[str]

@dataclass
class RedactionEvidence:
    redaction_id: str
    prompt_hash: str
    fields_redacted: list[str]
    fields_verified_absent: list[str]
    prompt_visible_leak_count: int
    verdict: str    # "pass" | "fail"

@dataclass
class PromptPack:
    prompt_pack_id: str
    react_state: str
    target_tier: str
    disclosure_phase: str
    source_refs: list[str]
    source_versions: dict
    candidate_summary: dict
    connector_constitution_cards: list[ConstitutionCard]
    tool_name_cards: list[ToolNameCard]
    policy_cards: list[PolicyCard]
    guide_cards: list[GuideCard]
    selected_schema_cards: list[SchemaCard]    # empty unless disclosure_phase=="schema_binding"
    decision_surface: str
    uncertainty_markers: list[str]
    omission_summary: str
    allowed_tool_calls: list[str]
    forbidden_tool_calls: list[str]
    allowed_next_actions: list[str]
    hil_options: list[dict]
    redaction_summary: RedactionEvidence
    expires_at: str

class PromptPackBuilder:
    def build(self,
              resolution_envelope: ResolutionEnvelope,
              disclosure_phase: str,
              prompt_budget_tokens: int,
              committed_tool_names: list[str] = None) -> PromptPack:
        """
        1. Build ConstitutionCards from connector manifests in CandidateUniverse.
           - plain-English only, no JSON manifests
        2. Build ToolNameCards from BindingBundle.tool_name_cards.
           - names and one-line descriptions ONLY (not full schemas, not required_inputs lists)
        3. Build PolicyCards from PolicyBundle.
        4. Build GuideCards from policy_bundle.guide_refs.
        5. If disclosure_phase == "schema_binding" and committed_tool_names provided:
             Build SchemaCards ONLY for committed tool names.
             SchemaCard.input_schema includes only the required + optional input fields.
             SchemaCard.input_schema MUST NOT include output_schema_ref or provider internals.
        6. Build candidate_summary:
             connector labels, person labels, resource labels, freshness flags.
             NO resource_ids, NO binding_id internals, NO connector provider routing.
        7. Build allowed_tool_calls from CandidateUniverse.allowed_next_actions.
        8. Build forbidden_tool_calls from CandidateUniverse.forbidden_next_actions.
        9. Build omission_summary from CandidateUniverse.omissions.
           If omissions exist: must be in omission_summary. Silent elision forbidden.
        10. Run redaction_check on the entire pack before returning.
            If any leak detected: raise PromptPackLeakError (do not return a leaking pack).
        """

    def _redact(self, obj: dict) -> dict:
        """Recursively remove known-secret fields: token, secret, credential, oauth, password, bearer, api_key."""

```text

**Phase-specific injection schedule (enforced, not optional):**

```python

PHASE_ALLOWED_FIELDS = {
    "loop_start": ["candidate_summary", "uncertainty_markers"],
    "connector_summary": ["connector_constitution_cards", "tool_name_cards",
                          "policy_cards", "guide_cards", "candidate_summary",
                          "omission_summary", "allowed_next_actions", "forbidden_next_actions"],
    "tool_name_selection": ["tool_name_cards", "allowed_next_actions",
                             "decision_surface", "hil_options"],
    "schema_binding": ["selected_schema_cards", "allowed_tool_calls"],
    "execution": ["allowed_tool_calls", "allowed_next_actions"]
}

```text

**If schema_binding phase is requested but committed_tool_names is empty or None:**
Raise `PromptPackPhaseError("schema_binding requires committed_tool_names")`.

**Runtime recovery contract:**
PromptPackBuilder must raise on leaks, and the ReAct loop must catch `PromptPackLeakError`, emit an audit record, and terminate with `ReactLoopResult(status="internal_error", error="prompt_pack_leak_detected")`. A prompt-pack leak must never crash the loop without an explicit result record.

**Acceptance criteria:**

```text

- connector_summary phase pack contains no schema content (selected_schema_cards=[]).
- schema_binding phase pack contains SchemaCards only for committed_tool_names.
- redaction_check on every built pack returns prompt_visible_leak_count=0.
- Build raises PromptPackLeakError if any secret field detected.
- omission_summary is non-empty when CandidateUniverse.omissions is non-empty.
- tool_name_cards contain name and description only — no required_inputs, no output_schema.

```text

**Proof command:**

```text

python scripts/probe_prompt_injection.py --json --record-proof

```text

---

### EPIC 4-B — Back Prompt Redesign

---

#### ISSUE-018 — Back system prompt for situated execution

**What to build:**
`poc/back_tool_contract/back_prompt_poc.py`

A `build_back_prompt_poc(envelope: BackTaskEnvelope, session_snapshot: dict, grounding_block: str) -> str` that generates the Back system prompt for the situated execution kernel.

**Prompt sections (in order):**

```python

BACK_SYSTEM_PROMPT_TEMPLATE = """
## Your Role
You are the Back execution actor for a household AI kernel.
Your job is to execute the task in the envelope below.
You are not allowed to speak to the user directly.
You are not allowed to claim a task is complete until you have evidence it is complete.
You are not allowed to call any tool not in your current allowed_next_actions.

## Task Envelope Summary
Task ID: {task_id}
Tier: {tier}
Safety Band: {safety_band}
Budget: {max_iterations} iterations, {max_fabric_calls} fabric calls

## What You Must Do
1. Call resolve_situation(request_frame_id, disclosure_phase="connector_summary") first.
2. Read the allowed_next_actions in the response. Do only those actions.
3. If the response says you need a prerequisite read: do the read before the write.
4. If the response says needs_disambiguation: call submit_result(result_type="needs_hil") with the disambiguation question.
5. When you have completed all required actions and have a VerificationObservation: call submit_result(result_type="completed").
6. If you cannot complete the task: call submit_result(result_type="cannot_execute") with a clear reason.

## What You Must Never Do
- Never call invoke_capability for a side-effecting operation without first calling resolve_situation.
- Never call a capability that is not in your allowed_next_actions.
- Never claim completed without a verification observation.
- Never invent resource IDs, event IDs, or person IDs.
- Never batch calls that depend on each other's results.

## Session State Snapshot
{session_snapshot_text}

## Grounding
{grounding_block}

## Current Task
{task_json}
"""

```text

**`session_snapshot_text` must be rendered from `session_snapshot` dict. Rules:**

```text

- Include: beliefs_active summary, task_state summary, persona preferences.
- Do NOT include: raw session blob, internal IDs, tokens, scores.
- Max length: 500 tokens. Truncate with "... (truncated for context budget)" if longer.

```text

**`task_json` must be rendered from `envelope.task_dispatch`. Rules:**

```text

- Include: intents, urgency, reference_context (user-world params only).
- Do NOT include: trace_id, session_id, internal routing fields (tier, safety_band already shown above).
- Must be valid JSON string embedded in the prompt.

```text

**Acceptance criteria:**

```text

- Built prompt contains task_id, tier, safety_band, max_iterations.
- Built prompt contains the six "What You Must Do" instructions.
- Built prompt contains the six "What You Must Never Do" instructions.
- Built prompt does NOT contain trace_id or session_id (those stay in ToolContext).
- Built prompt does NOT contain raw tokens or credentials.
- Session snapshot longer than 500 tokens is truncated with the truncation note.

```text

---

#### ISSUE-019 — resolve_situation tool declaration and execute function

**What to build:**
`poc/back_tool_contract/resolve_situation_tool.py`

The LLM-facing tool declaration and the execute function that Back's react loop calls when the model chooses `resolve_situation`.

**Tool declaration (OpenAI function-call format):**

```python

RESOLVE_SITUATION_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "resolve_situation",
        "description": (
            "Resolve the current situation and get what I am allowed to do next. "
            "I must call this before any side-effecting operation. "
            "Returns allowed_next_actions, resource summaries, and connector guidance. "
            "Call with disclosure_phase='connector_summary' first. "
            "Then commit tool names at 'tool_name_selection'. "
            "Then get full schemas at 'schema_binding'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request_frame_id": {
                    "type": "string",
                    "description": "The request frame ID from the current task context"
                },
                "disclosure_phase": {
                    "type": "string",
                    "enum": ["connector_summary", "tool_name_selection", "schema_binding", "execution"],
                    "description": "What level of information I need"
                },
                "committed_tool_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tool names I have committed to use (required at schema_binding phase)"
                },
                "previous_resolution_id": {
                    "type": "string",
                    "description": "Prior resolution ID if refreshing"
                }
            },
            "required": ["request_frame_id", "disclosure_phase"]
        }
    }
}

```text

**`execute_resolve_situation(args: dict, ctx: ToolContext) -> ToolResult`:**

```python

def execute_resolve_situation(args: dict, ctx: ToolContext) -> ToolResult:
    """
    1. Load RequestFrame from ctx.request_frame_store[args.request_frame_id].
       If not found: return ToolResult(status="error", error="request_frame_not_found").
    2. Build ResolveSituationRequest, including ctx.completed_prerequisite_bindings.
    3. Call ctx.resolver.resolve(request).
    4. Store ResolutionEnvelope in ctx.resolution_store[resolution_id].
    5. Inject PromptPack into ctx.prompt_injection_queue for this iteration.
    5a. Update ctx.allowed_capability_names from the returned BindingBundle/ResolutionEnvelope.
    6. Build compact tool result visible to LLM:
         resolution_id
         verdict
         candidate_summary (labels only, no internal IDs)
         allowed_next_actions (plain English list)
         forbidden_next_actions (plain English list)
         guide (one-paragraph summary of what to do next)
         missing_fields (if any)
         needs_disambiguation (bool)
         hil_options (if needs_disambiguation)
    7. Return ToolResult(status="ok", data=compact_result).
    """

```text

**Compact result contract:**

```text

The compact result the LLM sees must:
  - Contain allowed_next_actions as plain-English strings, not binding_id internals.
  - Contain resource labels, not resource IDs.
  - NOT contain resolution_envelope internals (ScopeProof, PolicyBundle raw).
  - Translate binding references to human-readable action descriptions:
    "invoke bind_001" -> "Check for conflicts in family calendar (list_events)"
    "invoke bind_002" -> "Create the dentist appointment in family calendar (create_event)"

```text

**Acceptance criteria:**

```text

- Call with valid request_frame_id returns verdict and allowed_next_actions.
- Call with missing request_frame_id returns error, not exception.
- Compact result contains no resource_ids or binding_id raw hashes.
- Compact result allowed_next_actions are plain-English descriptions.
- PromptPack is injected into ctx.prompt_injection_queue after every call.
- ctx.allowed_capability_names is updated from machine-readable binding/capability metadata, not from plain-English allowed_next_actions.

```text

---

#### ISSUE-019A — invoke_capability tool declaration and execute function

**What to build:**
`poc/back_tool_contract/invoke_capability_tool.py`

The LLM-facing schema for the capability invocation tool and the executor that turns a model request into an `InvocationRequest`.

**Tool declaration:**

```python

INVOKE_CAPABILITY_TOOL_SCHEMA = {
  "type": "function",
  "function": {
    "name": "invoke_capability",
    "description": (
      "Invoke exactly one capability that resolve_situation has allowed. "
      "Use a capability_name only if it appears in the current allowed actions. "
      "Do not invoke side-effecting capabilities until prerequisite reads are complete."
    ),
    "parameters": {
      "type": "object",
      "properties": {
        "capability_name": {
          "type": "string",
          "description": "Exact capability name from the current allowed capability set"
        },
        "binding_id": {
          "type": "string",
          "description": "Binding ID from the current ResolutionEnvelope when available"
        },
        "params": {
          "type": "object",
          "description": "Capability input params matching the schema exposed at schema_binding phase"
        },
        "idempotency_key": {
          "type": "string",
          "description": "Required for writes and side effects; stable per intended effect"
        }
      },
      "required": ["capability_name", "params"]
    }
  }
}

```text

**Design decision:**
The model may pass `capability_name` because it is visible in ToolNameCards. `binding_id` is optional and preferred when visible at schema-binding/execution phases. The dispatcher must authorize against `ReactLoopState.allowed_capability_names` and the current binding store; it must not authorize by matching the plain-English `allowed_next_actions` strings.

**`execute_invoke_capability(args: dict, ctx: ToolContext) -> ToolResult`:**

```python

def execute_invoke_capability(args: dict, ctx: ToolContext) -> ToolResult:
  """
  1. Require ctx.last_resolution_id; otherwise return must_call_resolve_situation_first.
  2. Require args.capability_name in ctx.allowed_capability_names.
  3. Resolve binding_id from args.binding_id or from ctx.capability_name_to_binding.
  4. Validate idempotency_key for write/side_effect bindings.
  5. Build InvocationRequest and call InvocationRuntime.invoke.
  6. If a prerequisite read succeeds, add its binding_id to ctx.completed_prerequisite_bindings.
  7. Return a safe ToolResult with status, summary, recovery, and verifier obligation.
  """

```text

**Acceptance criteria:**

```text

- Tool schema requires capability_name and params.
- Side-effecting invocation without idempotency_key returns typed error.
- capability_name not in ctx.allowed_capability_names returns typed error.
- Successful prerequisite read updates ctx.completed_prerequisite_bindings.
- ToolResult contains no raw provider payload, tokens, or internal resource IDs.

```text

---

## MILESTONE 5 — Back ReAct Loop Redesign

**Goal:** The POC Back ReAct loop runs against a real LLM, uses resolve_situation before any side effect, follows allowed_next_actions, and terminates correctly. No canned model responses anywhere.

---

### EPIC 5-A — ReAct Loop Core

---

#### ISSUE-020 — POC ReAct loop with situated execution contract

**What to build:**
`poc/back_tool_contract/back_react_loop_poc.py`

A full `back_react_loop_poc` function that runs the Back loop against a real LLM and enforces the authority contract at the dispatcher.

**Function signature:**

```python

async def back_react_loop_poc(
    envelope: BackTaskEnvelope,
    model_client: ModelClient,    # real model client, no mock
    resolver: ResolveSituationService,
    invocation_runtime: InvocationRuntime,
    prompt_pack_builder: PromptPackBuilder,
    verification_runner: VerificationPlanRunner,
    local_store: LocalProjectionStore,
    global_store: GlobalProjectionStore,
    proof_writer: ProofRecordWriter
) -> ReactLoopResult

```text

**Loop structure:**

```python

class ReactLoopState:
    iteration: int = 0
    request_frame: RequestFrame | None = None
    last_resolution_id: str | None = None
    prerequisite_reads_completed: set[str] = field(default_factory=set)
  completed_prerequisite_bindings: set[str] = field(default_factory=set)
  allowed_capability_names: set[str] = field(default_factory=set)
  capability_name_to_binding: dict[str, str] = field(default_factory=dict)
    invocations_completed: list[str] = field(default_factory=list)
    verification_observations: list[VerificationObservation] = field(default_factory=list)
    prompt_injection_queue: list[PromptPack] = field(default_factory=list)
    submit_result_called: bool = False
    final_result: dict | None = None

async def back_react_loop_poc(...) -> ReactLoopResult:
    state = ReactLoopState()

    # Build RequestFrame and store it
    request_frame = RequestFrameBuilder().build(envelope)
    state.request_frame = request_frame
    frame_store = {request_frame.request_id: request_frame}

    # Build initial system prompt
    system_prompt = build_back_prompt_poc(envelope, session_snapshot, grounding_block)

    # Build initial messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps({
            "task": "Execute the task in the envelope above.",
            "request_frame_id": request_frame.request_id
        })}
    ]

    # Tools available at loop start
    tools = [RESOLVE_SITUATION_TOOL_SCHEMA, INVOKE_CAPABILITY_TOOL_SCHEMA,
             SUBMIT_RESULT_TOOL_SCHEMA]

    for iteration in range(envelope.budget.max_iterations):
        state.iteration = iteration

        # Inject pending PromptPack as a system message if queued
        try:
          for pack in state.prompt_injection_queue:
            messages.append({"role": "system", "content": render_prompt_pack(pack)})
          state.prompt_injection_queue.clear()
        except PromptPackLeakError as exc:
          write_audit_record("prompt_pack_leak_detected", {"error": str(exc)})
          return ReactLoopResult(status="internal_error",
                       error="prompt_pack_leak_detected",
                       evidence=str(exc))

        # Call real LLM — no mocking here
        response = await model_client.chat(
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        # Parse tool calls from response
        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            # No tool call: nudge (not error) at early iterations
            if iteration < 2:
                messages.append(nudge_no_tool_call(iteration))
                continue
            else:
                return ReactLoopResult(status="missing_submit_result",
                                       error="model_stopped_without_submit")

        # Process tool calls
        for call in tool_calls:
            result = await dispatch_tool_call(call, state, ...)
            messages.append(tool_result_to_message(call.id, result))

            if state.submit_result_called:
                return ReactLoopResult(
                    status=state.final_result["result_type"],
                    result=state.final_result
                )

    return ReactLoopResult(status="budget_exhausted",
                           error=f"no submit_result after {envelope.budget.max_iterations} iterations")

```text

**`dispatch_tool_call` enforces authority gates:**

```python

async def dispatch_tool_call(call: ToolCall, state: ReactLoopState, ...) -> ToolResult:
    """
    GATE 1: If call.name in ["invoke_capability", "batch_invoke_capabilities"]:
      Check state.last_resolution_id is not None.
      If None: return ToolResult(status="error",
                                  error="must_call_resolve_situation_first",
                                  recovery="Call resolve_situation before invoking capabilities.")

    GATE 2: If call.name == "invoke_capability":
      Check that args.capability_name is in state.allowed_capability_names.
      Do NOT compare against plain-English allowed_next_actions strings.
      If not: return ToolResult(status="error",
                                 error="capability_not_in_allowed_next_actions",
                                 recovery=f"Allowed: {sorted(state.allowed_capability_names)}. Call resolve_situation again if needed.")

    GATE 3: If call.name == "invoke_capability" and capability is a write:
      Check prerequisite reads are complete for this capability's connector.
      If not: return ToolResult(status="error",
                                 error="prerequisite_read_not_completed",
                                 recovery="Run list_events first to check for conflicts.")

    GATE 4: If call.name == "submit_result" and result_type == "completed":
      Check state.verification_observations is not empty.
      If empty: return ToolResult(status="error",
                                   error="completed_requires_verification_observation",
                                   recovery="Run verification read first, then submit_result.")

    If all gates pass: dispatch to the correct handler.
    """

```text

**Acceptance criteria:**

```text

- Loop calls real LLM with tool_choice="auto" on every iteration.
- Gate 1: invoke_capability without prior resolve_situation returns error, loop continues.
- Gate 2: invoke_capability with name not in allowed_next_actions returns error, loop continues.
- Gate 2 checks allowed_capability_names, not human-readable allowed_next_actions strings.
- Gate 3: write before prerequisite read returns error, loop continues.
- Gate 4: submit_result(completed) without verification returns error, loop continues.
- PromptPackLeakError is caught and returned as ReactLoopResult(status="internal_error", error="prompt_pack_leak_detected") with audit evidence.
- Loop terminates when submit_result is called by model.
- Loop terminates with budget_exhausted if max_iterations reached.
- No iteration uses a mocked model response (assert model_client is not MockModelClient).

```text

---

#### ISSUE-021 — ModelClient abstraction and real LLM wiring

**What to build:**
`poc/back_tool_contract/model_client.py

A `ModelClient` protocol/ABC and concrete implementations for each model backend.

**Protocol:**

```python

from typing import Protocol

class ModelClient(Protocol):
    async def chat(self,
                   messages: list[dict],
                   tools: list[dict],
                   tool_choice: str = "auto",
                   temperature: float = 0.0,
                   max_tokens: int = 4096) -> ModelResponse: ...

    @property
    def model_id(self) -> str: ...

    @property
    def is_mock(self) -> bool:
        """Must return False for all real clients. Proof harness checks this."""

```text

**Concrete implementations (no mock):**

```python

class GeminiModelClient:
    """Uses google.generativeai or vertexai SDK. Real API calls."""
    def __init__(self, model_name: str, project: str = None, location: str = None)
    @property
    def is_mock(self) -> bool: return False

class OpenAIModelClient:
    """Uses openai SDK. Real API calls."""
    def __init__(self, model_name: str, api_key_env: str = "OPENAI_API_KEY")
    @property
    def is_mock(self) -> bool: return False

class AnthropicModelClient:
    """Uses anthropic SDK. Real API calls."""
    def __init__(self, model_name: str, api_key_env: str = "ANTHROPIC_API_KEY")
    @property
    def is_mock(self) -> bool: return False

```text

**`ModelResponse` type:**

```python

@dataclass
class ToolCall:
    id: str
    name: str
    args: dict

@dataclass
class ModelResponse:
    model_id: str
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str    # "tool_calls" | "stop" | "length" | "error"
    usage: dict           # {"prompt_tokens": int, "completion_tokens": int}

```text

**Tool call argument normalization:**

```python

def extract_tool_calls(response: ModelResponse) -> list[ToolCall]:
    """
    Each model returns tool calls in a slightly different shape.
    This must normalize across Gemini, OpenAI, and Anthropic formats.
    Must parse args from JSON string if the model returns string instead of dict.
    Must raise ToolCallParseError (not return empty) if args are unparseable.
    """

```text

**Acceptance criteria:**

```text

- GeminiModelClient.is_mock returns False.
- OpenAIModelClient.is_mock returns False.
- All clients implement the ModelClient protocol fully.
- extract_tool_calls handles Gemini, OpenAI, and Anthropic response formats correctly.
- parse failure raises ToolCallParseError, not silently returns empty list.

```text

---

#### ISSUE-022 — PromptPack injection rendering

**What to build:**
`poc/back_tool_contract/prompt_injection.py` (extend from ISSUE-017)

A `render_prompt_pack(pack: PromptPack) -> str` function that turns a PromptPack into a compact system message for injection into the message list.

**Rendering rules:**

```text

Constitution cards:
  "## Connector Guide: {label}
   Before you can {operation}: {preconditions list}
   After {write_operation}: {verification_requirement}"

Tool name cards:
  "## Available Actions
   {capability_name}: {description} (role: {role})"
   NO schema details here.

Policy cards:
  "## Policy
   Allowed for this operation: {what_is_required}
   Will trigger human review: {what_triggers_hil}
   Denied: {what_is_denied}"

Guide cards:
  "## Guide: {title}
   {content}"

Schema cards (only at schema_binding phase):
  "## Schema for {capability_name}
   Required fields: {required_fields}
   Full schema:
   ```json
   {input_schema}
   ```"

Allowed/forbidden actions:
  "## You may do:
   {allowed_next_actions}
   ## You must NOT do yet:
   {forbidden_next_actions}"

Omission summary (if not empty):
  "## Note: Some connectors were excluded
   {omission_summary}"

```text

**Token budget enforcement:**
If rendered text exceeds `pack.max_tool_calls * 200` tokens (rough estimate), truncate guide_cards first, then policy card detail, preserving tool name cards and allowed/forbidden actions.

**Acceptance criteria:**

```text

- Rendered prompt for connector_summary phase contains no JSON schemas.
- Rendered prompt for schema_binding phase contains JSON schema for committed tools.
- Token budget truncation preserves allowed_next_actions and tool_name_cards.
- Rendered prompt contains no token/secret/credential fields.

```text

---

## MILESTONE 6 — Invocation Runtime

**Goal:** InvocationRequest preflight, InvocationObservation normalization, native provider path, Bridge path, and IFL adapter path all work and produce structured proof records.

---

### EPIC 6-A — Invocation Preflight And Dispatch

---

#### ISSUE-023 — InvocationRuntime and preflight

**What to build:**
`poc/back_tool_contract/invocation_runtime.py`

**Types:**

```python

@dataclass
class InvocationRequest:
    invocation_id: str
    resolution_id: str
    binding_id: str
    capability_name: str
    params: dict
    idempotency_key: str
    actor_ref: str
    safety_context: dict
    policy_gate_refs: list[str]
    expected_effect: str
    verifier_requested: bool
    created_at: str

@dataclass
class InvocationObservation:
    invocation_id: str
    binding_id: str
    status: str    # "success" | "partial" | "failed" | "denied" | "needs_hil" | "retryable"
    provider_status: str
    result_summary: str
    artifacts: dict
    structured_result: dict    # safe subset of provider result
    errors: ErrorObservation | None
    recovery_directive: RecoveryDirective | None
    verifier_obligation: dict | None
    allowed_next_actions: list[str]
    audit_fields: dict          # NOT sent to LLM
    latency_ms: int

class InvocationRuntime:
    def __init__(self, binding_store: dict,    # binding_id -> CapabilityBinding
                 resolution_store: dict,        # resolution_id -> ResolutionEnvelope
                 idempotency_store: IdempotencyStore,
                 native_provider: NativeProviderDispatch,
                 bridge_dispatch: BridgeDispatch | None)

    async def invoke(self, request: InvocationRequest) -> InvocationObservation:
        """
        PREFLIGHT (in order, stop on first failure):

        1. Binding lookup: binding_store.get(request.binding_id)
           If not found: return failed(error="binding_not_found")
           If expired (now > binding.expires_at): return denied(error="stale_binding",
               recovery=RecoveryDirective(action="refresh_projection"))

        2. Resolution freshness: resolution_store.get(request.resolution_id)
           If expired: return denied(error="stale_resolution",
               recovery=RecoveryDirective(action="refresh_projection"))

        3. Param validation: validate request.params against binding.input_schema_ref.
           Load schema from global_store. Run jsonschema.validate.
           If invalid: return failed(error="capability_params_incomplete",
               recovery=RecoveryDirective(action="retry_with_params",
                   suggested_params_patch=compute_patch(request.params, schema)))

        4. Idempotency check: idempotency_store.check(request.idempotency_key)
           If previously succeeded: return prior observation (no-op, not error)
           If in flight: return retryable(error="idempotency_conflict_in_flight")

        5. Safety mapping: check request.safety_context.safety_band >= binding.safety_requirement
           If mismatch: return denied(error="safety_band_mismatch",
               recovery=RecoveryDirective(action="block_and_submit"),
               safety_mapping_evidence=SafetyMappingEvidence(...))

        6. Resource freshness re-check for writes:
           local_store.get_connected_resource(binding.resource_id).freshness_state
           If stale and write: return denied(error="stale_projection_at_invocation",
               recovery=RecoveryDirective(action="refresh_projection"))

        DISPATCH (after preflight passes):
        7. Route to native_provider or bridge based on binding.connector_id connector_type.
        8. Execute with timeout.
        9. Record idempotency result.
        10. Build InvocationObservation.
        11. Trigger ProjectionDeltaIngester for read results.
        """

```text

**Acceptance criteria:**

```text

- Valid calendar create request passes all preflight and dispatches to native_provider.
- Expired binding returns denied with recovery=refresh_projection.
- Missing required param returns failed with suggested_params_patch.
- Duplicate idempotency key after success returns prior observation.
- Safety band mismatch returns denied with SafetyMappingEvidence.
- Stale resource at invocation returns denied.
- All 40 connectors' required param schemas validated in preflight.

```text

**Proof command:**

```text

python scripts/probe_invoke_by_binding.py --json --record-proof

```text

---

#### ISSUE-024 — Idempotency store

**What to build:**
`poc/back_tool_contract/stores/idempotency_store.py`

```python

class IdempotencyStore:
    """SQLite-backed idempotency key tracking."""

    def check(self, idempotency_key: str) -> IdempotencyCheckResult:
        """
        Return IdempotencyCheckResult:
          state: "not_seen" | "in_flight" | "succeeded" | "failed"
          prior_observation: InvocationObservation | None (if succeeded)
        """

    def mark_in_flight(self, idempotency_key: str, invocation_id: str) -> None
    def mark_success(self, idempotency_key: str, observation: dict) -> None
    def mark_failed(self, idempotency_key: str, error: str) -> None

```text

**Schema:**

```sql

CREATE TABLE IF NOT EXISTS idempotency_records (
  idempotency_key   TEXT PRIMARY KEY,
  state             TEXT NOT NULL CHECK(state IN ('in_flight','succeeded','failed')),
  invocation_id     TEXT NOT NULL,
  observation_json  TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

```text

**Acceptance criteria:**

```text

- check on unknown key returns "not_seen".
- mark_in_flight + check returns "in_flight".
- mark_success + check returns "succeeded" with prior_observation.
- Second mark_success for same key is a no-op (does not raise).

```text

---

#### ISSUE-025 — NativeProviderDispatch

**What to build:**
`poc/back_tool_contract/native_provider_dispatch.py`

A `NativeProviderDispatch` that routes invocations to the real `NativeToolProvider` and `ToolRegistry` from the existing production code, not a reimplementation.

**This is NOT a new native provider:**

```python

class NativeProviderDispatch:
    """
    Wraps the existing k1/tools/family/* production code.
    Does NOT reimplement family tool handlers.
    Routes invocations by connector_id to the real native tool services.
    """
    def __init__(self, tool_registry: ToolRegistry)

    async def dispatch(self, capability_name: str, params: dict,
                       write_context: WriteContext) -> NativeProviderResult:
        """
        1. Parse connector_id and action_name from capability_name.
           (format: tool.{effect}.{connector_id}.{action_name})
            Connector IDs may contain underscores and action names may contain underscores.
            Parse from the left: segment 0 = "tool", segment 1 = effect,
            the final segment = action_name, and all middle segments joined by "." or "_"
            according to the manifest index identify connector_id. Never split
            `tool.read.family_settings.get_visibility_policy` as connector_id="family".
        2. service = tool_registry.get_service(connector_id)
           If not found: raise NativeProviderNotFound(connector_id)
        3. result = await service.dispatch(action_name, params, write_context)
        4. Return NativeProviderResult(success=result.get("success"), data=result, latency_ms=...)
        """

```text

**WriteContext must be built from InvocationRequest, not from a static config:**

```python

def build_write_context_from_invocation(
    request: InvocationRequest,
    binding: CapabilityBinding,
    actor_id: str
) -> WriteContext:
    return WriteContext(
        user_id=actor_id,
        role=request.safety_context.get("actor_role", "parent"),
        band=request.safety_context.get("safety_band", "GREEN"),
        space_id=request.safety_context.get("space_id"),
        idempotency_key=request.idempotency_key,
        trace_id=request.audit_fields.get("trace_id"),
        session_id=request.audit_fields.get("session_id")
    )

```text

**Acceptance criteria:**

```text

- dispatch("tool.read.calendar.list_events", params, ctx) calls real calendar service.
- dispatch("tool.execute.calendar.create_event", params, ctx) creates real event in SQLite.
- Unknown connector_id raises NativeProviderNotFound.
- Multi-part connector IDs such as family_settings parse correctly.
- WriteContext.role and .band are derived from InvocationRequest, not hardcoded.

```text

---

#### ISSUE-026 — BridgeDispatch for bridge and IFL connectors

**What to build:**
`poc/back_tool_contract/connector_dispatch.py`

A `BridgeDispatch` that routes invocations to the real `ConnectorGateway` from `bridge/connector/gateway.py`.

```python

class BridgeDispatch:
    def __init__(self, gateway: ConnectorGateway)

    async def dispatch(self, connector_id: str, tool_name: str,
                       params: dict, caller: ConnectorCaller) -> BridgeDispatchObservation:
        """
        1. Map connector_id to adapter_id used by ConnectorGateway.
        2. Build ConnectorCaller from InvocationRequest actor_ref and safety_context.
        3. result = await gateway.invoke(adapter_id, tool_name, params, caller)
        4. Return BridgeDispatchObservation:
             adapter_id, tool_name, success, data, error_code, error_message, latency_ms
             raw_ref = reference to full result (not included in prompt-visible content)
        """

@dataclass
class BridgeDispatchObservation:
    adapter_id: str
    tool_name: str
    success: bool
    data: dict       # safe subset only — no raw HTTP bodies, no tokens
    error_code: str | None
    error_message: str | None
    raw_ref: str     # opaque reference to full result stored separately
    latency_ms: int

```text

**Acceptance criteria:**

```text

- Dispatches to real ConnectorGateway (not a stub gateway).
- data field contains only safe fields — no token, no authorization header, no full HTTP body.
- raw_ref is set to an opaque reference (file path or key), never to raw content.
- Error from ConnectorGateway is normalized to BridgeDispatchObservation with success=False.

```text

**Proof command:**

```text

python scripts/probe_bridge_dispatch.py --json --record-proof

```text

---

#### ISSUE-027 — IFL adapter runtime path

**What to build:**
`poc/back_tool_contract/ifl_adapter_runtime.py`

`IflAdapterRuntime` that wraps the real Google Calendar IFL adapter from `bridge/ifl/adapters/google_calendar/`.

```python

@dataclass
class IflCommandEnvelope:
    adapter_id: str
    command: str
    args: dict
    caller: dict
    trace_id: str

@dataclass
class IflResultEnvelope:
    adapter_id: str
    command: str
    success: bool
    result: dict        # adapter-specific safe fields
    error_code: str | None
    error_message: str | None
    raw_payload_ref: str    # reference to full raw response, kept hidden from LLM

class IflAdapterRuntime:
    def __init__(self, gateway: ConnectorGateway)

    async def execute(self, envelope: IflCommandEnvelope) -> IflResultEnvelope:
        """
        1. Build ConnectorCaller from envelope.caller.
        2. gateway.invoke(envelope.adapter_id, envelope.command, envelope.args, caller)
        3. Store raw result in a separate store with a ref key.
        4. Build IflResultEnvelope with safe fields only.
        5. raw_payload_ref points to the stored raw result, not the raw content itself.
        """

```text

**Acceptance criteria:**

```text

- execute with google_calendar_read adapter and events_list command reaches real IFL adapter.
- IflResultEnvelope.result contains events list, not raw HTTP response.
- raw_payload_ref is set, IflResultEnvelope.result is not the raw payload.
- Error from adapter produces success=False with error_code.

```text

**Proof command:**

```text

python scripts/probe_ifl_adapter.py --json --record-proof

```text

---

## MILESTONE 7 — Verification And SubmitResult Authority

**Goal:** Every write operation is verified before completed is legal. SubmitResult authority gate enforces evidence requirements. All typed error paths work.

---

### EPIC 7-A — Verification Runner

---

#### ISSUE-028 — VerificationPlanRunner

**What to build:**
`poc/back_tool_contract/verification_runner.py`

**Types:**

```python

@dataclass
class VerificationPlan:
    verification_plan_id: str
    resolution_id: str
    binding_id: str
    invocation_id: str
    verifier_ref: str
    verifier_method: str    # "read_after_write" | "output_schema" | "state_compare" | "none_available"
    expected_effect: str
    expected_resource_state: dict
    readback_capability_ref: str | None
    readback_params: dict | None
    max_staleness_ms: int
    degraded_completion_policy: str | None    # None means degraded completion is forbidden
    required_for_submit_status: str    # "completed" | "partial" | "audit_only"

@dataclass
class VerificationObservation:
    verification_id: str
    verification_plan_id: str
    status: str    # "verified" | "degraded_verified" | "failed" | "inconclusive" | "skipped_by_policy" | "unavailable"
    observed_effect: str | None
    observed_resource_state_ref: str | None
    mismatch_summary: str | None
    stale_read_summary: str | None
    degraded_reason: str | None
    recovery_directive: RecoveryDirective | None
    proof_refs: list[str]

class VerificationPlanRunner:
    def __init__(self, invocation_runtime: InvocationRuntime,
                 local_store: LocalProjectionStore)

    async def build_plan(self, binding: CapabilityBinding,
                          observation: InvocationObservation,
                          constitution: dict) -> VerificationPlan:
        """
        Build VerificationPlan from:
          constitution.verification[operation] -> method
          observation.artifacts (e.g., event_id for read-after-write)
          binding.verifier_ref

        If method == "read_after_write":
          readback_capability_ref = constitution.verification[operation].readback_capability
          readback_params = build from observation.artifacts + binding.resource_id
        If method == "none_available":
          degraded_completion_policy must be set from connector manifest or None.
        """

    async def run(self, plan: VerificationPlan) -> VerificationObservation:
        """
        If plan.verifier_method == "read_after_write":
          1. Build InvocationRequest for the readback capability.
          2. Execute read via invocation_runtime.invoke.
          3. Compare observation.structured_result against plan.expected_resource_state.
          4. If fields match: return VerificationObservation(status="verified").
          5. If read returned nothing: return status="failed".
          6. If read is older than max_staleness_ms: return status="inconclusive".

        If plan.verifier_method == "output_schema":
          1. Validate the original invocation observation.structured_result
             against the output schema from the capability contract.
          2. If valid: return status="verified".
          3. If invalid: return status="failed" with mismatch_summary.

        If plan.verifier_method == "none_available":
          If plan.degraded_completion_policy is not None:
            return status="degraded_verified" with degraded_reason set.
          Else:
            return status="unavailable".
            (submit_result(completed) will be blocked — this is correct behavior)
        """

```text

**Acceptance criteria:**

```text

- create_event then get_event produces VerificationObservation(status="verified").
- create_event then get_event returning wrong title produces status="failed".
- create_event then get_event stale (manipulate observed_at) produces status="inconclusive".
- none_available without degraded_completion_policy produces status="unavailable".
- none_available with degraded_completion_policy produces status="degraded_verified".

```text

**Proof command:**

```text

python scripts/probe_resolution_executor.py --json --record-proof

```text

---

### EPIC 7-B — ErrorObservation, RecoveryDirective, HIL

---

#### ISSUE-029 — ErrorObservation and RecoveryDirective types

**What to build:**
`poc/back_tool_contract/error_types.py`

```python

@dataclass
class ErrorObservation:
    error_id: str
    source_component: str    # "invocation_preflight" | "native_provider" | "bridge" | "ifl" | "verification" | "dispatcher"
    code: str
    severity: str            # "recoverable" | "degraded" | "terminal"
    retryability: str        # "retry_with_patch" | "retry_later" | "no_retry"
    user_visible_summary: str
    developer_code: str
    context: dict            # structured error context

@dataclass
class RecoveryDirective:
    recovery_id: str
    error_id: str
    action: str    # "ask_hil" | "retry_with_params" | "refresh_projection" |
                   # "run_prerequisite_read" | "choose_from_candidates" |
                   # "block_and_submit" | "cannot_execute"
    suggested_params_patch: dict | None
    required_fields: list[str]
    candidate_refs: list[dict]
    hil_options: list[dict] | None
    block_reason: str | None

```text

**Error code taxonomy (must be exhaustive):**

```text

binding_not_found
stale_binding
stale_resolution
capability_params_incomplete
missing_idempotency_key
idempotency_conflict_in_flight
safety_band_mismatch
stale_projection_at_invocation
policy_gate_expired
policy_deny
native_provider_error
bridge_dispatch_error
ifl_adapter_error
verification_failed
verification_inconclusive
verification_unavailable
budget_exhausted
must_call_resolve_situation_first
capability_not_in_allowed_next_actions
prerequisite_read_not_completed
completed_requires_verification_observation

```text

**Every error code must have a corresponding `make_{code}(...)` factory function.**

**Acceptance criteria:**

```text

- Every error code constant has a make_ factory.
- make_capability_params_incomplete includes suggested_params_patch computation.
- RecoveryDirective.action is always one of the defined action values.
- ErrorObservation.user_visible_summary is plain English (no internal IDs, no stack traces).

```text

---

#### ISSUE-030 — HIL request and resume path

**What to build:**
`poc/back_tool_contract/hil.py`

```python

@dataclass
class HILRequest:
    hil_request_id: str
    task_id: str
    resolution_id: str
    hil_type: str       # "disambiguation" | "missing_input" | "confirmation" | "risk_acknowledgement"
    prompt: str
    options: list[dict] | None
    required: bool
    context_summary: str
    expires_at: str

@dataclass
class HILResponse:
    hil_response_id: str
    hil_request_id: str
    selected_option_id: str | None
    freeform_input: str | None
    responded_at: str

class HILPort:
    """POC implementation: synchronous in-memory HIL for automated testing."""

    def __init__(self, auto_responses: dict[str, HILResponse] = None)
        # auto_responses: {hil_request_id: HILResponse} for scenario-driven testing

    async def request(self, hil_request: HILRequest) -> HILResponse:
        """
        In automated scenario runs: look up auto_responses[hil_request_id].
        If not found in auto_responses: raise HILTimeoutError (do not invent a response).
        Do NOT return a default response — missing HIL response must be a real failure.
        """

    async def resolve(self, response: HILResponse) -> None:
        """Record that a HIL response was received."""

```text

**Acceptance criteria:**

```text

- HILPort.request with auto_response returns the scripted response.
- HILPort.request without auto_response raises HILTimeoutError.
- HIL resume path: disambiguation response updates local projection alias for resolved person.
- After HIL response, re-resolution with updated context produces can_execute verdict.

```text

---

### EPIC 7-C — SubmitResult Authority Gate

---

#### ISSUE-031 — SubmitResult authority gate and execute function

**What to build:**
`poc/back_tool_contract/submit_result_gate.py`

**Tool schema:**

```python

SUBMIT_RESULT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_result",
        "description": "Submit the final result of this task. Only call when done.",
        "parameters": {
            "type": "object",
            "properties": {
                "result_type": {
                    "type": "string",
                    "enum": ["completed", "partial", "needs_hil", "cannot_execute", "failed", "blocked"]
                },
                "summary": {"type": "string"},
                "artifacts": {"type": "object"},
                "unresolved_intents": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string", "description": "Required for non-completed results"}
            },
            "required": ["result_type", "summary"]
        }
    }
}

```text

**`execute_submit_result(args: dict, loop_state: ReactLoopState, ...) -> ToolResult`:**

```python

def execute_submit_result(args: dict, loop_state: ReactLoopState,
                           resolution_id: str) -> SubmitResultGateResult:
    """
    AUTHORITY GATE (checked in order):

    1. result_type == "completed":
       REQUIRE: loop_state.verification_observations is not empty.
       REQUIRE: at least one VerificationObservation.status in ["verified", "degraded_verified"].
       REQUIRE: loop_state.invocations_completed is not empty.
       If failed: return GATE_BLOCKED(error="completed_requires_verification_evidence")

    2. result_type == "completed":
       REQUIRE: resolution_id is not None (resolve_situation was called).
       If failed: return GATE_BLOCKED(error="completed_requires_prior_resolution")

    3. result_type == "needs_hil":
       REQUIRE: a HILRequest was emitted in this loop (loop_state.hil_request_emitted).
       If failed: return GATE_BLOCKED(error="needs_hil_requires_hil_request_first")

    4. result_type == "cannot_execute" or "failed" or "blocked":
       REQUIRE: args.reason is set and not empty.
       If failed: return GATE_BLOCKED(error="non_completion_requires_reason")

    If all gates pass:
      Build SubmitResult record with evidence.
      Set loop_state.submit_result_called = True.
      Set loop_state.final_result = SubmitResult.
      Return SubmitResultGateResult(accepted=True, submit_result=...)
    """

```text

**Acceptance criteria:**

```text

- completed without VerificationObservation returns GATE_BLOCKED.
- completed without prior resolution returns GATE_BLOCKED.
- completed with verified VerificationObservation passes gate.
- degraded_verified VerificationObservation passes gate for completed.
- unavailable VerificationObservation blocks completed (must use partial or cannot_execute).
- cannot_execute without reason returns GATE_BLOCKED.
- needs_hil without prior HILRequest returns GATE_BLOCKED.

```text

**Proof command:**

```text

python scripts/probe_resolution_executor.py --full --json --record-proof

```text

---

## MILESTONE 8 — End-To-End And Model Matrix

**Goal:** All 100 scenarios run end-to-end with real LLMs. Model matrix covers 3 model classes. All proof records have all_pass=true and llm_mock_used=false.

---

### EPIC 8-A — End-To-End Scenario Runner

---

#### ISSUE-032 — ResolutionExecutor (M12A) — single scenario end-to-end

**What to build:**
`poc/back_tool_contract/resolution_executor.py`

`ResolutionExecutor` that runs one scenario end-to-end from BackTaskEnvelope to SubmitResult.

```python

class ResolutionExecutor:
    def __init__(self,
                 model_client: ModelClient,
                 resolver: ResolveSituationService,
                 invocation_runtime: InvocationRuntime,
                 verification_runner: VerificationPlanRunner,
                 hil_port: HILPort,
                 proof_writer: ProofRecordWriter,
                 global_store: GlobalProjectionStore,
                 local_store: LocalProjectionStore)

    async def execute(self, scenario: dict,
                       actor_config: dict) -> ResolutionExecutorResult:
        """
        1. Build BackTaskEnvelope from scenario.
        2. Call back_react_loop_poc(...) with real model_client.
        3. Assert loop_result.status matches scenario.expected_submit_status.
        4. Assert resolution envelope verdict matches scenario.expected_resolution_verdict.
        5. Assert all negative_assertions are satisfied.
        6. Write proof record with all assertions.
        7. Return ResolutionExecutorResult.
        """

```text

**Negative assertion evaluation:**

Each `scenario.negative_assertions` entry is a typed object. Write an `evaluate_negative_assertion(assertion: NegativeAssertion, loop_trace: LoopTrace) -> NegativeAssertionResult` that:

```text

- Checks `assertion.assertion_type` and `assertion.params` against actual loop behavior recorded in LoopTrace.
- LoopTrace records: all tool calls made, all tool results, all PromptPack injections.
- Assertions like "resolver must not return can_execute without prerequisite read" check
  whether the loop ever received a can_execute verdict when prerequisite reads were not done.
- Assertions like "create_event must not be in allowed_next_actions at Phase 1" check
  PromptPack injections for Phase 1.
- If an assertion cannot be evaluated: return status="skip" with `skip_reason`, not status="pass".
- Plain-English text is never parsed as the source of truth; it is for humans only.

```text

**M12A special scenario — duplicate path HIL gate (S097):**

```text

Scenario: user wants to create an event that already exists in the calendar.
Expected: prerequisite list_events reveals conflict -> HIL triggered (not write proceeding).
Assert: create_event binding never executed.
Assert: HILRequest emitted with conflict context.
Assert: submit_result result_type = "needs_hil".

```text

**Acceptance criteria:**

```text

- Single-connector write scenarios (S036-S060) all complete with status=completed.
- Disambiguation scenarios (S076-S085) all produce needs_hil or missing_required_params.
- S097 (conflict detected) produces needs_hil and does not execute create_event.
- S100 (duplicate idempotency) produces completed (no-op, prior result returned).
- All proof records have llm_mock_used=false.

```text

**Proof command:**

```text

python scripts/probe_resolution_executor.py --all-scenarios --json --record-proof

```text

---

#### ISSUE-033 — Full 100-scenario E2E runner (M12)

**What to build:**
`poc/back_tool_contract/e2e_scenario_gate.py`

```python

class E2EScenarioGate:
    def __init__(self, executor: ResolutionExecutor,
                 scenario_corpus: list[dict],
                 model_clients: dict[str, ModelClient])

    async def run_all(self, model_id: str,
                       scenario_filter: list[str] = None) -> E2ERunReport:
        """
        For each scenario in corpus (or filtered subset):
          1. Create an isolated in-memory LocalProjectionStore for the scenario.
             Do not share a local SQLite file across concurrent scenario runs.
          2. Seed the fixture into that per-scenario store.
          3. Create a fresh per-run IdempotencyStore.
          4. Reuse GlobalProjectionStore only as read-only after manifest admission.
          5. Run executor.execute(scenario, actor_config).
          6. Collect result into E2ERunReport.

        Return E2ERunReport with:
          model_id, total_scenarios, passed, failed, skipped,
          failures: [{scenario_id, expected_status, actual_status, assertion_failures}],
          all_pass: bool
        """

```text

**Acceptance criteria:**

```text

- All 100 scenarios produce a result (no unhandled exceptions).
- E2ERunReport.all_pass is True for at least Gemini Pro and GPT-4o.
- Failed scenarios log enough detail to diagnose the failure.
- No scenario uses a mocked model response.
- Parallel model matrix runs use isolated LocalProjectionStore and IdempotencyStore instances per scenario.

```text

**Proof command:**

```text

python scripts/probe_e2e_scenarios.py --production-provider --json --record-proof

```text

---

### EPIC 8-B — Model Matrix

---

#### ISSUE-034 — Model matrix runner

**What to build:**
`poc/back_tool_contract/model_matrix_runner.py`

```python

class ModelMatrixRunner:
    def __init__(self, gate: E2EScenarioGate, proof_writer: ProofRecordWriter)

    async def run_matrix(self, model_ids: list[str],
                          scenario_filter: list[str] = None) -> ModelMatrixReport:
        """
        For each model_id:
          1. Run E2EScenarioGate.run_all(model_id, scenario_filter).
          2. Compute per-model metrics:
               tool_call_compliance_rate: % of scenarios where resolve_situation called before invoke
               prerequisite_read_compliance_rate: % where prereq reads done before writes
               disambiguation_compliance_rate: % of S076-S085 where needs_hil produced
               hallucination_rate: % where model invented a resource_id or binding_id not in resolution
               submit_result_on_completion_rate: % of scenarios that terminated with submit_result
          3. Determine per-model verdict: "pass" | "pass_with_minor_failures" | "fail"
             pass: all_pass=True
             pass_with_minor_failures: >=90% pass rate, hallucination_rate < 0.05
             fail: <90% pass rate or hallucination_rate >= 0.05

        Return ModelMatrixReport with per-model results and overall recommendation.
        """

```text

**Hallucination detection:**

```python

def detect_hallucination(loop_trace: LoopTrace,
                          resolution_envelope: ResolutionEnvelope) -> list[str]:
    """
    Walk loop_trace.tool_calls.
    For each invoke_capability call:
      Check if capability_name appears in resolution_envelope.candidate_universe.capability_bindings.
      If not: record as hallucinated_capability.
    For each param value that looks like an ID (starts with "resource." or "calendar." etc):
      Check if it appears in resolution_envelope.candidate_universe.resource_candidates.
      If not: record as hallucinated_resource_id.
    Return list of hallucinated items.
    """

```text

**Minimum model matrix to run:**

```text

gemini-2.5-pro
gemini-2.0-flash
gpt-4o
gpt-4o-mini
claude-sonnet-4-6  (or latest Claude available)

```text

**Acceptance criteria:**

```text

- All 5 models complete the matrix run.
- gemini-2.5-pro and gpt-4o achieve verdict="pass" or "pass_with_minor_failures".
- No model has hallucination_rate > 0.10.
- ModelMatrixReport.json written to tmp/back_tool_contract/model_matrix/.
- Production migration is blocked unless at least 2 models achieve "pass" verdict.

```text

**Proof command:**

```text

python scripts/probe_e2e_scenarios.py --production-provider --all-models --json --record-proof

```text

---

#### ISSUE-035 — ShadowComparisonRecord for each seam

**What to build:**
`poc/back_tool_contract/shadow_comparison.py`

For each component, run the same 100 scenarios through both the current path (`discover_capabilities -> invoke_capability`) and the new path (`resolve_situation -> binding_id -> invocation`) and produce a comparison.

Old-path and new-path runs must use separate ReactLoopState, local projection store, idempotency store, and audit buffers. Sharing state between the two shadow paths is forbidden because it can hide regressions or mutate the comparison baseline.

```python

@dataclass
class ShadowComparisonRecord:
    seam_id: str
    component: str
    scenarios_run: int
    new_path_pass: int
    old_path_pass: int
    new_path_only_pass: int    # new path caught an error old path missed
    old_path_only_pass: int    # old path did something new path blocked (investigate)
    equivalence_rate: float
    improvement_areas: list[str]    # cases where new path is provably better
    regression_risks: list[str]     # cases where old path worked and new path didn't
    recommendation: str             # "cutover" | "more_work" | "do_not_cutover"
    generated_at: str

```text

**Recommendation rule:**

```text

"cutover" when:
  new_path_pass >= old_path_pass AND equivalence_rate >= 0.95 AND regression_risks is empty

"more_work" when:
  regression_risks is not empty OR equivalence_rate < 0.95

"do_not_cutover" when:
  new_path_pass < old_path_pass OR any critical regression risk

```text

**Acceptance criteria:**

```text

- ShadowComparisonRecord produced for each of: resolver, binding, invocation, verification, submit_result gate.
- At least 3 of 5 components produce recommendation="cutover" before production migration begins.
- regression_risks list is documented, not empty by default.
- Old-path and new-path execution state are isolated in the same process.

```text

---

## MILESTONE 9 — Regression And Targeted Tests

**Goal:** Every existing production test that touches Back, Fabric, and FSM continues to pass. No production code changed yet.

---

### EPIC 9-A — Non-Regression Checks

---

#### ISSUE-036 — Verify existing Back/Fabric tests still pass

**What to run:**

```text

pytest tests/k1/concierge/actors/test_back.py -v
pytest tests/k1/concierge/tools/test_implementations.py -v
pytest tests/k1/fabric/ -v

```text

**What to assert:**
Nothing in Milestone 0-8 work has changed any file outside `poc/back_tool_contract/` or `scripts/probe_*.py`.

**Acceptance criteria:**

```text

- All existing k1/concierge and k1/fabric tests pass.
- No import added to production k1/ files.
- No existing production behavior modified.

```text

---

## Summary — Issue Dependency Order

```text

Foundation:
  ISSUE-001 (proof.py)
  ISSUE-002 (_probe_common.py)
  ISSUE-003 (global_projection_store.py)
  ISSUE-004 (local_projection_store.py)

Corpus (can parallel with stores):
  ISSUE-005 (100 scenarios)
  ISSUE-006 (40 connector manifests)

Milestone 1 — builds on stores + corpus:
  ISSUE-007 (manifest admission) <- 003, 006
  ISSUE-008 (100k scale) <- 007
  ISSUE-009 (household fixture) <- 004, 005
  ISSUE-010 (projection delta) <- 004

Milestone 2 — builds on all above:
  ISSUE-011 (BackTaskEnvelope) <- 001, 002
  ISSUE-012 (RequestFrameBuilder) <- 011
  ISSUE-013 (ResolveSituationService) <- 012, 014, 015, 016, 017

Milestone 3 — can parallel inside:
  ISSUE-014 (resource resolution) <- 003, 004
  ISSUE-015 (policy selector) <- 003
  ISSUE-016 (capability binder) <- 003, 004

Milestone 4:
  ISSUE-017 (PromptPackBuilder) <- 016, 015
  ISSUE-018 (Back system prompt) <- 011, 012
  ISSUE-019 (resolve_situation tool) <- 013, 017
  ISSUE-019A (invoke_capability tool) <- 016, 019, 023

Milestone 5:
  ISSUE-020 (ReAct loop) <- 018, 019, 019A, 023, 031
  ISSUE-021 (ModelClient) <- none (standalone)
  ISSUE-022 (PromptPack rendering) <- 017

Milestone 6:
  ISSUE-023 (InvocationRuntime) <- 016, 024, 025, 026
  ISSUE-024 (IdempotencyStore) <- 003
  ISSUE-025 (NativeProviderDispatch) <- existing k1/tools/family
  ISSUE-026 (BridgeDispatch) <- existing bridge/connector
  ISSUE-027 (IflAdapterRuntime) <- existing bridge/ifl

Milestone 7:
  ISSUE-028 (VerificationPlanRunner) <- 023
  ISSUE-029 (ErrorObservation types) <- none (types only)
  ISSUE-030 (HIL) <- none
  ISSUE-031 (SubmitResult gate) <- 028, 029, 030

Milestone 8:
  ISSUE-032 (ResolutionExecutor M12A) <- all above
  ISSUE-033 (E2E 100 scenarios M12) <- 032
  ISSUE-034 (model matrix) <- 033
  ISSUE-035 (shadow comparison) <- 033

Milestone 9:
  ISSUE-036 (non-regression) <- all above

```text
