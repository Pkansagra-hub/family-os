# Phase 1 Fabric Enhancement — Milestone Epic & Issues

> **Milestone:** GATE-P1 — Fabric standalone proven.
> **Branch:** `feature/prompt-architecture-refactor`
> **Start:** 2026-06-04
> **Target:** All 10 promoted components in `k1/fabric/`, all 223 existing tests pass, all 18 new test files pass (GAP-P1-001 through GAP-P1-023), benchmark matches or exceeds POC.
> **Predecessor:** None (Phase 1 is the foundation)
> **Successor:** Phase 1.1 — Family Tool Constitution Enrichment (Epics 9–14)

---

## Epic 0: Directory Scaffold

**Goal:** Create the directory structure so promoted files have somewhere to land.

### Issue 0.1 — Create store directories

- **Files:** `k1/fabric/stores/__init__.py` (empty)
- **Files:** `k1/fabric/verification/__init__.py` (empty)
- **Files:** `k1/fabric/constitution/__init__.py` (empty)
- **Files:** `k1/fabric/prompt_pack/__init__.py` (empty)
- **Files:** `k1/fabric/resolver/__init__.py` (empty)
- **Files:** `k1/fabric/connectors/__init__.py` (empty)
- **Verify:** `python -c "import k1.fabric.stores; import k1.fabric.resolver; import k1.fabric.constitution; import k1.fabric.prompt_pack; import k1.fabric.connectors"`

---

## Epic 1: Foundation — Stores

**Goal:** Build the three storage components from the whiteboard Component 1, 2, and 3 designs. The POC proves the approach (SQLite WAL, FTS5 content-sync, bulk chunking, graph traversal, state machine). The whiteboard defines the API. We build the whiteboard API clean.

**POC role:** Reference implementation for techniques — how FTS5 content-sync works, how `bulk_upsert_capabilities` chunks at 25K, how graph ontology tables are queried for typed resolution, how idempotency state machine enforces immutable-succeeded via SQL WHERE clause. The POC is NOT the spec. The whiteboard is the spec.

---

### Issue 1.1 — GlobalProjectionStore: Record Dataclasses

- **File:** `k1/fabric/stores/global_projection_store.py`
- **What:** 4 typed dataclasses per whiteboard §1.7. These are the return types for all query methods.

  ```python
  @dataclass
  class ConnectorRecord:
      connector_id: str
      label: str
      connector_type: str       # 'native' | 'bridge' | 'ifl'
      provider_type: str        # 'LOCAL' | 'MCP' | 'BRIDGE' | 'AGENT' | 'WORKFLOW'
      version: str
      admission_verdict: str    # 'admitted' | 'pending' | 'rejected'
      registration_type: str    # 'static' | 'dynamic' | 'discovered'
      constitution: dict = field(default_factory=dict)
      policy_declarations: dict = field(default_factory=dict)
      resource_kinds: list[str] = field(default_factory=list)
      created_at: str = ""
      updated_at: str = ""

  @dataclass
  class CapabilityRecord:
      capability_name: str            # "tool.execute.family.calendar.create"
      connector_id: str               # "family.calendar"
      invocation_mode: str            # 'read' | 'execute'
      action_name: str                # 'list' | 'search' | 'create' | 'update' | 'delete' | 'send'
      effect: str                     # 'read' | 'write' | 'delete' | 'compute'
      resource_kind: str | None       # "calendar_event"
      description: str = ""
      required_inputs: list[dict] = field(default_factory=list)
      optional_inputs: list[dict] = field(default_factory=list)
      output_schema_ref: str | None = None
      safety_band_min: str = "GREEN"
      risk_class: str = "benign"
      idempotency: str | None = None  # 'safe' | 'unsafe' | None
      compensation_capability: str | None = None
      record_type: str = "executable_capability"
      created_at: str = ""
      contract_json: dict = field(default_factory=dict)
      synthetic: bool = False

      # NOTE: capability_name is the single PK in the capabilities table.
      # Multi-resource projection lives in capability_type_index, which has
      # one row per (capability_name, resource_family, operation_family, effect).
      # Do NOT create duplicate capability rows per resource_kind.

  @dataclass
  class ResourceKindRecord:
      kind_id: str              # e.g. 'calendar.event', 'task.item'
      connector_id: str
      label: str
      schema: dict = field(default_factory=dict)
      verifier_affordances: list[str] = field(default_factory=list)

  @dataclass
  class ConstitutionRecord:
      connector_id: str
      constitution_id: str
      schema_version: str = "1.0.0"
      authored_by: str | None = None
      authored_at: str | None = None
      last_proven_at: str | None = None
      execution_phases: list[str] = field(default_factory=list)
      prerequisite_reads: list[dict] = field(default_factory=list)
      conflict_analysis_rules: list[dict] = field(default_factory=list)
      hil_gates: list[dict] = field(default_factory=list)
      mutation_sequencing: list[dict] = field(default_factory=list)
      verification_requirements: list[dict] = field(default_factory=list)
      companion_resource_roles: list[dict] = field(default_factory=list)
      precondition_summary: str | None = None
      companion_resource_summary: str | None = None
      hil_trigger_summary: str | None = None
      degradation_policy: str | None = None
  ```

### Issue 1.2 — GlobalProjectionStore: SQL Schema

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()` method
- **What:** 10 tables + 1 FTS5 index. This is the whiteboard Component 1 §1.2 schema plus the 5 graph ontology tables (documented here since the whiteboard omits them).
- **Tables:**

  ```sql
  -- 1. Connectors
  CREATE TABLE IF NOT EXISTS connectors (
      connector_id    TEXT PRIMARY KEY,
      label           TEXT NOT NULL,
      connector_type  TEXT NOT NULL CHECK(connector_type IN ('native','bridge','ifl')),
      provider_type   TEXT NOT NULL,
      version         TEXT NOT NULL DEFAULT '1.0.0',
      admission_verdict TEXT NOT NULL CHECK(admission_verdict IN ('admitted','pending','rejected')),
      registration_type TEXT NOT NULL CHECK(registration_type IN ('static','dynamic','discovered')),
      constitution_json TEXT NOT NULL DEFAULT '{}',
      policy_json     TEXT NOT NULL DEFAULT '{}',
      resource_kinds_json TEXT NOT NULL DEFAULT '[]',
      created_at      TEXT NOT NULL,
      updated_at      TEXT NOT NULL
  );

  -- 2. Capabilities
  CREATE TABLE IF NOT EXISTS capabilities (
      capability_name TEXT PRIMARY KEY,
      connector_id    TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
      invocation_mode TEXT NOT NULL CHECK(invocation_mode IN ('read','execute')),
      action_name     TEXT NOT NULL,
      effect          TEXT NOT NULL CHECK(effect IN ('read','write','delete','compute')),
      resource_kind   TEXT,
      description     TEXT NOT NULL DEFAULT '',
      required_inputs_json TEXT NOT NULL DEFAULT '[]',
      optional_inputs_json TEXT NOT NULL DEFAULT '[]',
      output_schema_ref   TEXT,
      safety_band_min TEXT NOT NULL DEFAULT 'GREEN' CHECK(safety_band_min IN ('GREEN','AMBER','RED')),
      risk_class      TEXT NOT NULL DEFAULT 'benign',
      idempotency     TEXT CHECK(idempotency IS NULL OR idempotency IN ('safe','unsafe')),
      compensation_capability TEXT,
      record_type     TEXT NOT NULL CHECK(record_type IN ('executable_capability','activity_profile','workflow','agent')),
      created_at      TEXT NOT NULL,
      contract_json   TEXT NOT NULL,
      synthetic       INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX IF NOT EXISTS idx_capability_lookup
      ON capabilities(resource_kind, invocation_mode, effect, connector_id, record_type, safety_band_min);

  -- 3. FTS5 full-text search
  CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts USING fts5(
      capability_name, description, resource_kind, connector_id,
      content='capabilities', content_rowid='rowid'
  );

  -- 4. Resource kinds
  CREATE TABLE IF NOT EXISTS resource_kinds (
      kind_id         TEXT PRIMARY KEY,
      connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
      label           TEXT NOT NULL,
      schema_json     TEXT NOT NULL DEFAULT '{}',
      verifier_affordances_json TEXT NOT NULL DEFAULT '[]',
      created_at      TEXT NOT NULL
  );

  -- 5. Connector constitutions (per-connector, not per-operation)
  CREATE TABLE IF NOT EXISTS connector_constitutions (
      connector_id        TEXT PRIMARY KEY REFERENCES connectors(connector_id),
      constitution_id     TEXT NOT NULL,
      schema_version      TEXT NOT NULL DEFAULT '1.0.0',
      authored_by         TEXT,
      authored_at         TEXT,
      last_proven_at      TEXT,
      execution_phases_json       TEXT NOT NULL DEFAULT '[]',
      prerequisite_reads_json     TEXT NOT NULL DEFAULT '[]',
      conflict_analysis_rules_json TEXT NOT NULL DEFAULT '[]',
      hil_gates_json              TEXT NOT NULL DEFAULT '[]',
      mutation_sequencing_json    TEXT NOT NULL DEFAULT '[]',
      verification_requirements_json TEXT NOT NULL DEFAULT '[]',
      companion_resource_roles_json  TEXT NOT NULL DEFAULT '[]',
      precondition_summary        TEXT,
      companion_resource_summary  TEXT,
      hil_trigger_summary         TEXT,
      degradation_policy          TEXT
  );

  -- 6-10. Graph ontology tables
  CREATE TABLE IF NOT EXISTS concept_aliases (
      alias TEXT NOT NULL, canonical_concept TEXT NOT NULL, domain TEXT,
      weight REAL DEFAULT 1.0, generic INTEGER DEFAULT 0, source TEXT DEFAULT 'catalog',
      PRIMARY KEY(alias, canonical_concept, domain)
  );
  CREATE TABLE IF NOT EXISTS concept_resource_edges (
      concept TEXT NOT NULL, resource_family TEXT NOT NULL, domain TEXT NOT NULL,
      weight REAL DEFAULT 1.0,
      PRIMARY KEY(concept, resource_family, domain)
  );
  CREATE TABLE IF NOT EXISTS resource_connector_edges (
      domain TEXT NOT NULL, resource_family TEXT NOT NULL, connector_id TEXT NOT NULL,
      weight REAL DEFAULT 1.0,
      role TEXT NOT NULL DEFAULT 'primary',  -- 'primary' | 'companion' | 'verifier' | 'prerequisite'
      PRIMARY KEY(domain, resource_family, connector_id)
  );

  -- Operation equivalences: canonical → equivalent mapping
  CREATE TABLE IF NOT EXISTS operation_equivalences (
      canonical_operation TEXT NOT NULL,    -- 'list'
      equivalent_operation TEXT NOT NULL,   -- 'search'
      resource_family TEXT,                 -- NULL = applies to all
      domain TEXT,                          -- NULL = applies to all
      PRIMARY KEY(canonical_operation, equivalent_operation, resource_family, domain)
  );

  CREATE TABLE IF NOT EXISTS operation_aliases (
      alias TEXT NOT NULL, operation_family TEXT NOT NULL, effect TEXT NOT NULL,
      weight REAL DEFAULT 1.0, generic INTEGER DEFAULT 1,
      PRIMARY KEY(alias, operation_family)
  );
  CREATE TABLE IF NOT EXISTS capability_type_index (
      capability_name TEXT NOT NULL, connector_id TEXT NOT NULL, domain TEXT NOT NULL,
      resource_family TEXT NOT NULL, operation_family TEXT NOT NULL, effect TEXT NOT NULL,
      side_effect_class TEXT, risk_class TEXT,
      PRIMARY KEY(capability_name, resource_family, operation_family, effect)
  );
  ```

### Issue 1.3 — GlobalProjectionStore: Public API

- **What:** Full typed API. Every method returns dataclasses, not dicts.
- **Methods (22 total):**

  ```python
  class GlobalProjectionStore:
      # ── Lifecycle ──
      def __init__(self, db_path: str | Path) -> None
      def open(self) -> None                    # WAL mode, foreign_keys ON, _ensure_schema()
      def close(self) -> None

      # ── Connector CRUD ──
      def upsert_connector(self, connector: ConnectorRecord) -> None
      def get_connector(self, connector_id: str) -> ConnectorRecord | None
      def list_connectors(self, *, connector_type: str | None = None) -> list[ConnectorRecord]
      def delete_connector(self, connector_id: str) -> None         # CASCADE to capabilities
      def connector_exists(self, connector_id: str) -> bool

      # ── Capability CRUD ──
      def upsert_capability(self, capability: CapabilityRecord) -> None
      def bulk_upsert_capabilities(self, capabilities: list[CapabilityRecord], *, chunk_size: int = 25_000) -> None
      def get_capability(self, capability_name: str) -> CapabilityRecord | None
      def get_capabilities_by_connector(self, connector_id: str) -> list[CapabilityRecord]
      def delete_capability(self, capability_name: str) -> None
      def capability_exists(self, capability_name: str) -> bool
      def count_capabilities(self) -> int

      # ── FTS5 Search ──
      def search_capabilities(self, query: str, *, top_k: int = 20, connector_ids: list[str] | None = None) -> list[CapabilityRecord]
      def search_capabilities_by_domain(self, query: str, domains: list[str], *, top_k: int = 20) -> list[CapabilityRecord]
      def rebuild_fts_index(self) -> None

      # ── Resource Kinds ──
      def upsert_resource_kind(self, kind: ResourceKindRecord) -> None
      def get_resource_kinds_by_connector(self, connector_id: str) -> list[ResourceKindRecord]
      def get_resource_kind(self, kind_id: str) -> ResourceKindRecord | None

      # ── Constitutions ──
      def upsert_constitution(self, constitution: ConstitutionRecord) -> None
      def get_constitution(self, connector_id: str) -> ConstitutionRecord | None
      def list_constitutions(self) -> list[ConstitutionRecord]

      # ── Bulk ──
      def load_from_manifest_batch(self, batch: CapabilityRegistrationBatch) -> LoadResult

      # ── Graph ontology queries (for CapabilityTypeResolver) ──
      def resolve_concept(self, alias: str, domain: str = "") -> list[dict[str, Any]]
      def get_concept_resource_family(self, concept: str, domain: str = "") -> list[dict[str, Any]]
      def resolve_operation(self, alias: str, effect: str = "") -> list[dict[str, Any]]
      def lookup_capability_by_type(self, domain: str, resource_family: str, operation_family: str, effect: str) -> list[dict[str, Any]]

      # ── Graph ontology upserts ──
      def upsert_concept_alias(self, alias: str, canonical_concept: str, domain: str = "", weight: float = 1.0, generic: bool = False, source: str = "catalog") -> None
      def upsert_concept_resource_edge(self, concept: str, resource_family: str, domain: str, weight: float = 1.0) -> None
      def upsert_resource_connector_edge(self, domain: str, resource_family: str, connector_id: str, weight: float = 1.0, role: str = "primary") -> None
      def upsert_operation_alias(self, alias: str, operation_family: str, effect: str, weight: float = 1.0, generic: bool = True) -> None
      def upsert_operation_equivalence(self, canonical_operation: str, equivalent_operation: str, resource_family: str | None = None, domain: str | None = None) -> None
      def get_operation_equivalences(self, canonical_operation: str | None = None) -> list[dict[str, Any]]
      def upsert_capability_type_index(self, capability_name: str, connector_id: str, domain: str, resource_family: str, operation_family: str, effect: str, side_effect_class: str | None = None, risk_class: str | None = None) -> None
  ```

### Issue 1.4 — GlobalProjectionStore: Internal Design

- **What:** Implementation techniques proven by the POC, applied clean to the whiteboard schema.
- **FTS5 content-sync:** `capabilities` is the content table for `capabilities_fts`. On single `upsert_capability`, emit `INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')`. On `bulk_upsert_capabilities`, emit `'delete-all'` first, chunk-insert at 25K rows, then call `rebuild_fts_index()` once at the end.
- **Thread safety:** SQLite WAL mode + `check_same_thread=False`. No additional mutex — Fabric serializes writes through `CapabilityRegistryAPI`.
- **JSON columns:** All `*_json` columns use `json.dumps(sort_keys=True)` on write. Python-side fields are `dict`/`list`. Serialization inside the store, not at call sites.
- **`contract_json`:** Stores the full serialized `CapabilityContract` (the Fabric type) as a JSON blob. This is a COMPLETE copy — the `CapabilityRecord` fields are denormalized for querying; `contract_json` is the authoritative source for fields not in the denormalized columns.
- **`synthetic` flag:** `True` = scale-test generated. The resolver may deprioritize but must not filter out — benchmarks need them.
- **Cascade delete:** `DELETE FROM connectors WHERE connector_id = ?` cascades to `capabilities`, `resource_kinds`, `connector_constitutions`. FTS5 content-sync automatically removes orphaned rows.

### Issue 1.5 — LocalProjectionStore

- **File:** `k1/fabric/stores/local_projection_store.py`
- **Design:** Per whiteboard Component 2. Per-session store for connected resources, household members, alias resolution, projection snapshots.
- **4 tables:** `connected_resources`, `household_members`, `alias_index`, `resource_projection_snapshots`
- **API:**

  ```python
  class LocalProjectionStore:
      def __init__(self, db_path: str | Path) -> None
      def open(self) -> None
      def close(self) -> None

      def upsert_connected_resource(self, resource: dict) -> None
      def get_connected_resource(self, resource_id: str) -> dict | None
      def list_connected_resources(self, actor_id: str, *, resource_kind: str | None = None, status: str = "active") -> list[dict]

      def upsert_household_member(self, member: dict) -> None
      def get_household_member(self, person_id: str) -> dict | None

      def resolve_alias(self, alias: str, actor_id: str, *, entity_type: str | None = None) -> list[dict]
      def fuzzy_resolve_alias(self, alias: str, actor_id: str, *, entity_type: str | None = None) -> list[dict]
      def rebuild_alias_index(self, actor_id: str, space_id: str) -> None

      def upsert_projection_snapshot(self, snapshot: dict) -> None
      def get_fresh_snapshot(self, resource_id: str, max_age_seconds: int = 300) -> dict | None

      def mark_resource_stale(self, resource_id: str) -> None
      def mark_resource_fresh(self, resource_id: str) -> None
      def reset(self) -> None
  ```

- **Tests:** GAP-P1-004

### Issue 1.6 — IdempotencyStore

- **File:** `k1/fabric/stores/idempotency_store.py`
- **Design:** Per whiteboard Component 3. Prevents duplicate capability execution.
- **State machine:** `not_seen → in_flight → succeeded/failed`. `succeeded` is immutable.
- **API:**

  ```python
  @dataclass(frozen=True)
  class IdempotencyCheckResult:
      state: str                # "not_seen" | "in_flight" | "succeeded" | "failed"
      prior_observation: dict | None
      error: str | None

  class IdempotencyStore:
      def __init__(self, db_path: str | Path) -> None
      def open(self) -> None
      def close(self) -> None

      def check(self, idempotency_key: str) -> IdempotencyCheckResult
      def mark_in_flight(self, idempotency_key: str, invocation_id: str) -> None
      def mark_success(self, idempotency_key: str, observation: dict) -> None
      def mark_failed(self, idempotency_key: str, error: str) -> None
      def cleanup_expired(self, max_age_hours: int = 24) -> int
  ```

- **Enforcement:** `WHERE state NOT IN ('succeeded')` on `mark_in_flight` and `mark_failed` UPDATE statements prevents overwriting succeeded state.
- **Tests:** GAP-P1-005

### Issue 1.7 — Tests

- **GAP-P1-003:** `tests/k1/fabric/stores/test_global_projection_store.py`
  - `TestRecordDataclasses` — roundtrip all 4 record types through store
  - `TestConnectorCRUD` — full CRUD with typed returns, cascade delete
  - `TestCapabilityCRUD` — CRUD, bulk 10K with chunking, get by connector
  - `TestFTSSearch` — BM25 ranking, rebuild after bulk, filtered by connector_id
  - `TestSearchByDomain` — domain-filtered FTS5
  - `TestResourceKinds` — CRUD with schema + verifier affordances
  - `TestConstitutionCRUD` — full 17-field roundtrip
  - `TestGraphTables` — all 5 graph ontology tables
  - `TestScale` — bulk 100K, search <5ms, concurrent readers
  - `TestLoadFromManifestBatch` — atomic batch insert
- **GAP-P1-004:** `tests/k1/fabric/stores/test_local_projection_store.py`
  - `TestConnectedResources`, `TestHouseholdMembers`, `TestAliasIndex`, `TestProjectionSnapshots`
- **GAP-P1-005:** `tests/k1/fabric/stores/test_idempotency_store.py`
  - `TestStateMachine`, `TestImmutableSucceeded`, `TestReplay`, `TestTTLCleanup`, `TestConcurrentAccess`
- **Run:** `pytest tests/k1/fabric/stores/ -v`

---

## Epic 2: Connector Definitions — Domain Catalog

**Goal:** Define the typed data model for connector definitions and build the 50-connector domain catalog. This is the INPUT that feeds `ManifestAdmissionService` → `GlobalProjectionStore`. Each connector gets a full manifest: identity, capabilities, constitution, policy, guide cards, and ontology registration.

**Design principle:** The connector onboarding doc (`connector_onboarding_familyos.md`) defines WHAT a connector must declare. This epic defines the Python types for those declarations and builds the 50 seed connectors. Individual family tools get custom constitutions in Epics 9-13; this epic provides the domain-wide baseline.

### Issue 2.1 — Connector Definition Dataclasses

- **File:** `k1/fabric/connectors/definition.py` (NEW)
- **What:** Typed dataclasses matching the connector onboarding doc §1.1–§1.6. These are the Python API for declaring a connector — what a connector author writes.

  ```python
  @dataclass
  class CapabilityDefinition:
      """One operation a connector can perform. Matches onboarding §1.2."""
      name: str                          # action verb: "create_event", "list_events"
      invocation_mode: str               # 'read' | 'execute'
      effect: str                        # 'read' | 'write' | 'delete' | 'compute'
      resource_kind: str                 # e.g. "calendar_event"
      description: str
      required_inputs: list[InputFieldSpec] = field(default_factory=list)
      optional_inputs: list[InputFieldSpec] = field(default_factory=list)
      output_schema_ref: str | None = None
      safety_band_min: str = "GREEN"
      risk_class: str = "benign"
      idempotency: str | None = None     # 'safe' | 'unsafe' | None
      compensation_capability: str | None = None
      record_type: str = "executable_capability"
      # Full JSON Schemas (for GlobalProjectionStore) — nullable, falls back to InputFieldSpec
      input_schema: dict | None = None
      output_schema: dict | None = None

  @dataclass
  class InputFieldSpec:
      """Single input/output field. Skinny version of JSON Schema."""
      name: str
      type: str                          # 'string' | 'integer' | 'number' | 'boolean' | 'datetime' | 'object' | 'array'
      required: bool = False
      description: str = ""
      example: Any = None

  @dataclass
  class ConstitutionDefinition:
      """Connector execution contract. Matches onboarding §1.3."""
      connector_id: str = ""             # filled by builder
      constitution_id: str = ""
      schema_version: str = "1.0.0"
      authored_by: str | None = None
      authored_at: str | None = None
      execution_phases: list[str] = field(default_factory=list)
      prerequisite_reads: list[dict] = field(default_factory=list)
      conflict_analysis_rules: list[dict] = field(default_factory=list)
      companion_resource_roles: list[dict] = field(default_factory=list)
      hil_gates: list[dict] = field(default_factory=list)
      mutation_sequencing: list[dict] = field(default_factory=list)
      verification_requirements: list[dict] = field(default_factory=list)
      precondition_summary: str | None = None
      companion_resource_summary: str | None = None
      hil_trigger_summary: str | None = None
      degradation_policy: str | None = None

  @dataclass
  class PolicyDefinition:
      """Per-connector policy rules. Matches onboarding §1.4."""
      write_requires_actor_role: list[str] = field(default_factory=list)   # empty = default-allow
      read_allowed_roles: list[str] = field(default_factory=list)
      hil_triggers: list[dict] = field(default_factory=list)
      protected_resources: list[dict] = field(default_factory=list)

  @dataclass
  class GuideCardDefinition:
      """LLM-facing guidance card. Matches onboarding §1.5."""
      guide_id: str
      title: str
      content: str
      relevance: str = "always"          # 'always' | 'on_conflict' | 'on_error'
      disclosure_phase: str = "connector_summary"

  @dataclass
  class OntologyDefinition:
      """Domain ontology registration. Matches onboarding §1.6."""
      domain: str
      concept_aliases: list[dict] = field(default_factory=list)       # {alias, canonical_concept, weight}
      concept_resource_edges: list[dict] = field(default_factory=list) # {concept, resource_family, weight}
      resource_connector_edges: list[dict] = field(default_factory=list) # {resource_family, connector_id, weight, role}
      operation_aliases: list[dict] = field(default_factory=list)      # {alias, operation_family, effect}

  @dataclass
  class ConnectorDefinition:
      """Complete connector manifest. Matches onboarding §1.1."""
      connector_id: str                  # "family.calendar"
      connector_type: str = "native"     # 'native' | 'bridge' | 'ifl'
      provider_type: str = "LOCAL"
      label: str = ""
      description: str = ""
      version: str = "1.0.0"
      provider_id: str = ""              # derived: "native.{connector_id}"
      resource_kinds: list[str] = field(default_factory=list)
      actor_scope: list[str] = field(default_factory=lambda: ["parent", "admin", "system"])
      admission_verdict: str = "admitted"
      registration_type: str = "static"
      capabilities: list[CapabilityDefinition] = field(default_factory=list)
      constitution: ConstitutionDefinition | None = None
      policy: PolicyDefinition | None = None
      guide_cards: list[GuideCardDefinition] = field(default_factory=list)
      ontology: OntologyDefinition | None = None
  ```

### Issue 2.2 — Service Definition (Compact Input Format)

- **File:** `k1/fabric/connectors/definition.py`
- **What:** `ServiceDefinition` — a compact dataclass for defining a connector from minimal fields. The builder expands this into a full `ConnectorDefinition`. This is what the domain catalog uses to define 50 connectors from 50 service defs.

  ```python
  @dataclass
  class ServiceDefinition:
      """Compact connector definition. Expanded to ConnectorDefinition by the builder.
      This is the POC's DOMAINS[domain]['services'][n] dict, typed."""
      id: str                            # "calendar"
      label: str                         # "Calendar"
      resource: str                      # primary resource_kind: "calendar_event"
      resource_kinds: list[str] = field(default_factory=list)  # additional resource kinds
      desc: str = ""                     # description
      read_op: str = "list"             # read operation verb
      write_op: str | None = "create"   # write operation verb, None = read-only
      write_inputs: list[str] = field(default_factory=list)
      read_inputs: list[str] = field(default_factory=list)
      domain_tags: list[str] = field(default_factory=list)
  ```

### Issue 2.3 — Connector Builder

- **File:** `k1/fabric/connectors/builder.py` (NEW)
- **What:** `build_connector_definition(domain_id: str, svc: ServiceDefinition) -> ConnectorDefinition`
- **Logic (proven by POC `build_connector_manifest`, now typed):**
  1. Derive `connector_id = f"{domain_id}.{svc.id}"`
  2. Derive `provider_id = f"native.{connector_id}"`
  3. Determine `resource_kinds` = `[svc.resource] + svc.resource_kinds`
  4. For EACH resource_kind, generate a read capability (`invocation_mode='read'`, `effect='read'`, `name=f"{svc.read_op}"`)
  5. If `svc.write_op` is set, for EACH resource_kind generate:
     - Write capability (`invocation_mode='execute'`, `effect='write'`, `name=f"{svc.write_op}"`)
     - Update capability (`invocation_mode='execute'`, `effect='write'`, `name="update"`)
     - Delete capability (`invocation_mode='execute'`, `effect='delete'`, `name="delete"`)
  6. For communication connectors or connectors with notification semantics (e.g. messaging, team_chat, notifications), add a send capability (`invocation_mode='execute'`, `effect='write'`, `name="send"`).
     For time-aware connectors (calendar, meetings, appointments, reminders), ensure create/update/delete/list exist and the constitution includes conflict analysis rules + prerequisite reads — do NOT add `send` just because the connector has `start`/`end`.
  7. Build `ConstitutionDefinition` with sensible defaults:
     - `prerequisite_reads`: list before mutate
     - `hil_gates`: missing required fields → HIL
     - `verification_requirements`: read_after_write for write connectors
     - `mutation_sequencing`: list → mutate → list
  8. Build `PolicyDefinition` with default-allow
  9. Build identity ontology: `concept_aliases` + `concept_resource_edges` + `resource_connector_edges` for each resource_kind
  10. Build `operation_aliases` for common verbs
- **Capability naming:** `tool.{invocation_mode}.{domain_id}.{svc.id}.{name}` — e.g. `tool.read.family.calendar.list`

### Issue 2.4 — Domain Catalog: 50 Service Definitions

- **File:** `k1/fabric/connectors/domain_catalog.py`
- **What:** `DOMAIN_SERVICES: dict[str, list[ServiceDefinition]]` — 5 domains × 10 services = 50 `ServiceDefinition` instances. This is the source of truth for what connectors exist in the kernel.
- **Domains:**
  - `family`: calendar, tasks, reminders, chores, shopping, notes, contacts, habits, budgets, documents
  - `enterprise`: meetings, bug_tracker, feature_tracker, doc_repo, it_helpdesk, team_chat, tasks, code_review, oncall_schedule, analytics
  - `government`: permits, licenses, violations, meetings, records, inspections, tax_records, court_docket, dispatch, voter_registry
  - `agriculture`: field_planner, livestock, equipment_log, ag_weather, farm_inventory, soil_analyzer, irrigation, harvest_planner, grain_storage, market_prices
  - `healthcare`: ehr, appointments, prescriptions, lab_orders, messaging, imaging, billing, immunizations, referrals, vitals
- **Functions:**

  ```python
  def build_domain_corpus(domain_id: str) -> list[ConnectorDefinition]:
      """Build all ConnectorDefinitions for a domain."""
      services = DOMAIN_SERVICES[domain_id]
      return [build_connector_definition(domain_id, svc) for svc in services]

  def build_all_corpora() -> dict[str, list[ConnectorDefinition]]:
      """Build ConnectorDefinitions for all 5 domains."""
      return {did: build_domain_corpus(did) for did in DOMAIN_SERVICES}
  ```

- **Verify:** `python -c "from k1.fabric.connectors.domain_catalog import build_domain_corpus; m = build_domain_corpus('family'); assert len(m) == 10; c = m[0]; assert c.connector_id == 'family.calendar'; assert len(c.capabilities) >= 4"`

### Issue 2.5 — Connector Definition Tests

- **GAP-P1-015:** `tests/k1/fabric/connectors/test_definitions.py`
  - `TestConnectorDefinitionShape` — all 14 required fields present, capability naming convention followed
  - `TestBuilderGeneratesAllCapabilities` — for write-capable connector, verify read + write + update + delete generated per resource_kind
  - `TestBuilderGeneratesReadOnlyCapabilities` — for read-only connector (write_op=None), only read capabilities
  - `TestBuilderDerivesProviderId` — `provider_id = "native.{domain}.{service}"`
  - `TestBuilderConstitutionDefaults` — default constitution has prerequisite_reads, hil_gates, verification_requirements
  - `TestBuilderOntologyIdentity` — identity concept aliases + resource edges generated for each resource_kind
  - `TestAll50ConnectorsBuild` — `build_all_corpora()` returns 50 connectors, all valid
  - `TestCapabilityNamesUnique` — no duplicate capability names across all 50 connectors
- **Run:** `pytest tests/k1/fabric/connectors/test_definitions.py -v`

---

## Epic 3: Resolver Input Types — RequestFrame & Task Envelope

**Goal:** Define the structured input types that feed into `ResolveSituationService`. These are the contracts between Back (the LLM execution actor) and Fabric (the resolver). The types are clean dataclasses. The builder is a simple mapper — no keyword guessing, no heuristic derivation. Back provides explicit `operation_hint` and `resource_kind_hint`; the builder just constructs the frame.

**Design principle:** The whiteboard says "Back does ALL intent reasoning." The request frame types must carry Back's decisions as explicit fields. No guessing, no keyword matching, no fallback derivation. The POC's `OPERATION_KEYWORDS` and `RESOURCE_KIND_KEYWORDS` constants are removed — those belong in Back's prompt, not in Fabric's types.

### Issue 3.1 — BackTaskEnvelope (Contract CC-0)

- **File:** `k1/fabric/resolver/back_task_envelope.py`
- **Design:** The incoming task format from Back. This is what Back wraps around the user's utterance plus resolved context before calling `resolve_situation`.

  ```python
  @dataclass(frozen=True)
  class BackTaskBudget:
      max_iterations: int = 10
      max_fabric_calls: int = 20
      max_prompt_tokens: int = 8000

  @dataclass(frozen=True)
  class BackTaskEnvelope:
      envelope_id: str
      task_id: str
      trace_id: str
      session_id: str
      actor_id: str
      space_id: str
      tier: str                           # 'LOW' | 'MEDIUM' | 'HIGH'
      safety_band: str                    # 'GREEN' | 'AMBER' | 'RED'
      task_dispatch: dict                 # raw intents from Back's LLM extraction
      budget: BackTaskBudget
      session_state_ref: str | None = None
      grounding_envelope_id: str | None = None
      temporal_anchor_id: str | None = None
      spatial_context_id: str | None = None
      submitted_at: str = ""
  ```

- **Functions:**
  - `parse_back_task_envelope(payload: dict) -> BackTaskEnvelope` — validates tier, safety_band, required fields
  - `_parse_budget(value) -> BackTaskBudget`
  - `_required_str(payload, field) -> str`
  - `_required_int(payload, field) -> int`
  - `_optional_str(value) -> str | None`
- **Constants:** `VALID_TIERS = {"LOW","MEDIUM","HIGH"}`, `VALID_SAFETY_BANDS = {"GREEN","AMBER","RED"}`
- **Verify:** `python -c "from k1.fabric.resolver.back_task_envelope import parse_back_task_envelope, BackTaskEnvelope"`

### Issue 3.2 — RequestFrame Types (Contract A)

- **File:** `k1/fabric/resolver/request_frame.py`
- **Design:** The structured input to `ResolveSituationService.resolve()`. These are pure dataclasses — no builder logic, no keyword matching. Back populates every field explicitly.

  ```python
  @dataclass(frozen=True)
  class PersonRef:
      raw: str                           # "Riley", "Morgan"
      confidence: str                    # 'high' | 'medium' | 'low'
      needs_resolution: bool = True      # False = already resolved to person_id

  @dataclass(frozen=True)
  class ResourceRef:
      raw: str                           # "Riley's calendar", "family chores list"
      resource_kind_hint: str | None = None
      confidence: str = "medium"
      needs_resolution: bool = True

  @dataclass(frozen=True)
  class TimeWindowHint:
      raw_phrase: str                    # "next Monday at 3pm"
      resolved_start: str | None = None  # ISO 8601
      resolved_end: str | None = None
      confidence: str = "medium"

  @dataclass(frozen=True)
  class RequestFrameIntent:
      intent_id: str
      action: str                        # raw user action text: "Add dentist appointment"
      domain: str | None = None          # e.g. "family"
      operation_hint: str = ""           # e.g. "create", "list"
      resource_kind_hint: str | None = None  # e.g. "calendar_event"
      subject_hint: str | None = None    # e.g. "dentist appointment"
      params: dict = field(default_factory=dict)  # {person_hint: "Riley", time_hint: "next Monday at 3pm"}

  @dataclass(frozen=True)
  class RequestFrame:
      request_id: str
      task_id: str
      trace_id: str
      actor_id: str
      space_id: str
      intents: list[RequestFrameIntent]
      time_window_hint: TimeWindowHint | None = None
      person_refs: list[PersonRef] = field(default_factory=list)
      resource_refs: list[ResourceRef] = field(default_factory=list)
      safety_context: dict = field(default_factory=dict)
      target_tier: str = "tier2"
      resolution_mode: str = "execution"
      created_at: str = ""
  ```

- **Key:** No `OPERATION_KEYWORDS`, no `RESOURCE_KIND_KEYWORDS`, no `_derive_operation_hint`, no `_derive_resource_kind_hint`. Back provides these explicitly. The builder just maps fields from the envelope.
- **Verify:** `python -c "from k1.fabric.resolver.request_frame import RequestFrame, RequestFrameIntent, PersonRef, ResourceRef, TimeWindowHint"`

### Issue 3.3 — RequestFrameBuilder

- **File:** `k1/fabric/resolver/request_frame_builder.py`
- **Design:** Simple mapper — extracts fields from `BackTaskEnvelope.task_dispatch` into a `RequestFrame`. No guessing. No keyword heuristics. Back provides `operation_hint` and `resource_kind_hint` in the intents; the builder copies them.

  ```python
  class RequestFrameBuilder:
      def build(self, envelope: BackTaskEnvelope) -> RequestFrame:
          """Build a RequestFrame from a BackTaskEnvelope.
          Back is responsible for providing operation_hint and resource_kind_hint
          in each intent. This builder does NOT derive them."""
          raw_intents = envelope.task_dispatch.get("intents", [])
          intents = []
          person_refs = []
          resource_refs = []
          time_parts = []

          for raw in raw_intents:
              params = dict(raw.get("params") or {})
              intents.append(RequestFrameIntent(
                  intent_id=raw.get("intent_id", f"intent_{uuid.uuid4().hex[:8]}"),
                  action=raw.get("action", ""),
                  domain=raw.get("domain"),
                  operation_hint=raw.get("operation_hint", ""),
                  resource_kind_hint=raw.get("resource_kind_hint"),
                  subject_hint=raw.get("subject_hint"),
                  params=params,
              ))
              # Extract person refs from params
              for key in ("person_hint", "participant", "attendee", "for_person", "assignee"):
                  if key in params:
                      person_refs.append(PersonRef(raw=str(params[key]), confidence="medium"))
              # Extract resource refs
              for key in ("resource_hint", "calendar_hint", "list_hint"):
                  if key in params:
                      resource_refs.append(ResourceRef(raw=str(params[key]),
                          resource_kind_hint=raw.get("resource_kind_hint"), confidence="medium"))
              # Collect time hints
              for key in ("date", "time", "date_hint", "time_hint", "time_phrase"):
                  if key in params:
                      time_parts.append(str(params[key]))

          time_window = self._resolve_time_window(time_parts)
          return RequestFrame(
              request_id=f"req_{uuid.uuid4().hex[:16]}",
              task_id=envelope.task_id,
              trace_id=envelope.trace_id,
              actor_id=envelope.actor_id,
              space_id=envelope.space_id,
              intents=intents,
              time_window_hint=time_window,
              person_refs=_dedupe_person_refs(person_refs),
              resource_refs=_dedupe_resource_refs(resource_refs),
              safety_context={
                  "actor_role": envelope.task_dispatch.get("actor_role", "parent"),
                  "safety_band": envelope.safety_band,
                  "session_id": envelope.session_id,
                  "budget": envelope.budget.to_dict() if hasattr(envelope.budget, 'to_dict') else {},
              },
              target_tier="tier2",
              resolution_mode="execution",
              created_at=datetime.now(timezone.utc).isoformat(),
          )

      def _resolve_time_window(self, time_parts: list[str]) -> TimeWindowHint | None:
          """Resolve time phrases to ISO 8601 where possible. Best-effort — may return None."""
          # Handle "today", "tomorrow", "next Monday", "in two hours", ISO dates, AM/PM
          # Keep the POC's time resolution logic (it's deterministic, not LLM-based)
  ```

- **What's removed from POC:** `OPERATION_KEYWORDS`, `RESOURCE_KIND_KEYWORDS`, `_derive_operation_hint()`, `_derive_resource_kind_hint()`, `_intent_from_phrase()`. These were heuristic guesses that belong in Back's prompt, not in Fabric.
- **What's kept from POC:** Time resolution helpers (`_resolve_date`, `_apply_time`, `_has_explicit_time`, `_duration_minutes`) — these are deterministic datetime math, not LLM heuristics.
- **Test helper (separate function):** `build_frame_from_dict(data: dict, actor_id: str, space_id: str) -> RequestFrame` — for benchmarks and tests that bypass the envelope. Constructs a `RequestFrame` directly from a dict with `intents[]` and `person_refs[]`.

### Issue 3.4 — ResourceProjection (Contract B)

- **File:** `k1/fabric/resolver/resource_projection.py`
- **Design:** Resolves person/entity aliases and connected resources from `LocalProjectionStore` into a `ResourceUniverse`. This is the "local world projection" — what resources does THIS household/actor actually have connected?

  ```python
  @dataclass(frozen=True)
  class ResourceCandidate:
      resource_id: str
      label: str
      resource_kind: str
      connector_id: str                 # empty if needs_resolution=False
      actor_permission: str             # 'read_write' | 'read_only' | 'restricted' | 'none'
      freshness_state: str              # 'fresh' | 'stale' | 'unknown'
      aliases: list[str] = field(default_factory=list)
      admission_verdict: str | None = None

  @dataclass(frozen=True)
  class PersonCandidate:
      person_id: str
      label: str
      role: str
      linked_resource_ids: dict = field(default_factory=dict)
      resolved: bool = False

  @dataclass(frozen=True)
  class UnresolvedRef:
      raw: str
      entity_type: str                  # 'person' | 'resource'
      reason: str                       # 'not_found' | 'ambiguous'
      candidates: list[dict] = field(default_factory=list)

  @dataclass(frozen=True)
  class ScopeProof:
      scope_proof_id: str
      actor_id: str
      space_id: str
      projection_sources: list[dict] = field(default_factory=list)
      omissions: list[dict] = field(default_factory=list)
      exclusions: list[dict] = field(default_factory=list)
      completeness: str = "unknown"

  @dataclass(frozen=True)
  class ResourceUniverse:
      universe_id: str
      resource_candidates: list[ResourceCandidate]
      person_candidates: list[PersonCandidate]
      unresolved: list[UnresolvedRef]
      scope_proof: ScopeProof
      completeness: str                 # 'complete' | 'partial' | 'unknown'
      freshness: str                    # 'fresh' | 'stale' | 'unknown'

  class ResolveResourcesService:
      def __init__(self, global_store: GlobalProjectionStore, local_store: LocalProjectionStore): ...
      def resolve(self, frame: RequestFrame, actor_id: str, space_id: str) -> ResourceUniverse:
          """For each PersonRef and ResourceRef in the frame, resolve against
          LocalProjectionStore. Persons: alias_index → household_members.
          Resources: alias_index → connected_resources (if needs_resolution=True)
          or direct candidate (if needs_resolution=False)."""
  ```

- **Key design points:**
  - `needs_resolution=False` → creates a direct `ResourceCandidate` with `connector_id=""`. The capability binder searches by `resource_kind`, not connector_id.
  - `needs_resolution=True` → resolves through alias index → connected resource → `ResourceCandidate` with actual `connector_id`.
  - Ambiguous (>1 match) → `UnresolvedRef(reason='ambiguous')`
  - Not found → `UnresolvedRef(reason='not_found')`
  - `actor_permission` check: `restricted`/`none` → excluded; `read_only` + write intent → excluded
- **Verify:** `python -c "from k1.fabric.resolver.resource_projection import ResolveResourcesService, ResourceUniverse, ResourceCandidate"`

### Issue 3.5 — CapabilityTypeResolver

- **File:** `k1/fabric/resolver/capability_type_resolver.py`
- **Design:** Graph-based typed resolution. Traverses the 5 graph ontology tables in `GlobalProjectionStore` to deterministically map an intent (operation_hint + resource_kind_hint) to a specific capability. This is the typed alternative to BM25 semantic search — exact graph edges instead of fuzzy text matching.

  ```python
  @dataclass
  class ResolvedIntentType:
      intent_id: str
      domain: str
      resource_family: str | None
      operation_family: str
      effect: str                       # 'read' | 'write'
      role: str = "primary"             # 'primary' | 'companion' | 'prerequisite' | 'verifier'
      evidence: list[str]
      confidence: str                   # 'high' | 'medium' | 'low'
      rejected: list[dict]
      fallback_capabilities: list[dict]  # from capability_type_index lookup

  class CapabilityTypeResolver:
      def __init__(self, global_store: GlobalProjectionStore, local_store: LocalProjectionStore): ...
      def resolve(self, frame: RequestFrame, universe: ResourceUniverse) -> list[ResolvedIntentType]: ...

      # ── Internal 4-step traversal ──
      def _resolve_one(self, intent: RequestFrameIntent, universe: ResourceUniverse) -> ResolvedIntentType:
          """4-step graph traversal proven by POC benchmark:
          1. Resolve operation: operation_hint → (operation_family, effect)
             via universal aliases + operation_aliases graph table
          2. Resolve concept: resource_kind_hint → canonical concepts
             via concept_aliases graph table + action text extraction
          3. Map concept → resource_family
             via concept_resource_edges graph table
             fallback: try concept directly as resource_family via lookup_capability_by_type
             fallback: use resource_kind_hint as resource_family
          4. Typed capability lookup: domain + resource_family + operation_family + effect
             via capability_type_index graph table
          Confidence: ≥4 evidence edges → 'high', ≥2 → 'medium', else 'low'
          """
  ```

- **Constants:** `UNIVERSAL_OPERATION_ALIASES` — ~30 common LLM verbs mapped to `(operation_family, effect)`:
  - `"schedule"/"add"/"book"/"create"` → `("create", "write")`
  - `"find"/"search"/"list"/"show"/"check"` → `("list", "read")`
  - `"update"/"edit"/"change"/"move"` → `("update", "write")`
  - `"delete"/"remove"/"cancel"` → `("delete", "write")`
  - `"send"/"notify"/"message"/"share"` → `("send", "write")`
- **POC-proven:** 96% extraction pass rate, 7/8 commit accuracy with correct extraction. The graph tables work. The 4-step traversal works. The confidence scoring works.
- **Verify:** `python -c "from k1.fabric.resolver.capability_type_resolver import CapabilityTypeResolver, ResolvedIntentType"`

### Issue 3.6 — Tests

- **GAP-P1-016:** `tests/k1/fabric/resolver/test_request_frame.py`
  - `TestBackTaskEnvelope` — parse valid, reject invalid tier, reject missing fields, budget defaults
  - `TestRequestFrameBuilder` — builds frame from envelope with explicit hints (no keyword guessing), handles missing operation_hint, handles multiple intents, resolves time window
  - `TestRequestFrameTypes` — all dataclass fields present, frozen=True, serialization roundtrip

- **GAP-P1-017:** `tests/k1/fabric/resolver/test_resource_projection.py`
  - `TestResolvePerson` — exact alias match → PersonCandidate, fuzzy match, not_found, ambiguous (>1 match)
  - `TestResolveResource` — needs_resolution=True → connected resource with connector_id, needs_resolution=False → direct candidate with connector_id="", stale resource flagged, readonly+write intent → excluded
  - `TestUniverseCompleteness` — all resolved → 'complete', some unresolved → 'partial', all stale → 'stale'

- **GAP-P1-018:** `tests/k1/fabric/resolver/test_capability_type_resolver.py`
  - `TestOperationResolution` — "create" → ("create","write"), "list" → ("list","read"), unknown → default
  - `TestConceptResolution` — exact concept_alias match, fallback to action text extraction, no match → empty
  - `TestResourceFamilyMapping` — concept→resource_family edge found, missing edge → fallback to direct concept lookup, missing both → fallback to rk_hint
  - `TestTypedLookup` — capability_type_index returns match, no match → empty fallback_capabilities
  - `TestConfidenceScoring` — 4 evidence → 'high', 2-3 → 'medium', 0-1 → 'low'
  - `TestEndToEnd` — "create/calendar_event/family" → resolves to tool.execute.family.calendar.create with high confidence

- **Run:** `pytest tests/k1/fabric/resolver/test_request_frame.py tests/k1/fabric/resolver/test_resource_projection.py tests/k1/fabric/resolver/test_capability_type_resolver.py -v`

---

## Epic 4: Governance — Policy, Verification, Admission

**Goal:** Build the three governance services that sit between the resolver input types (Epic 3) and the orchestrator (Epic 6). These enforce the rules: what's allowed, what must be verified, and what gets admitted into the store.

**System context:**

```
ResourceUniverse + operations → PolicySelector → PolicyBundle (gates resolution)
CapabilityBinding + observation → VerificationPlanRunner → VerificationObservation (gates submission)
ConnectorDefinition → ManifestAdmissionService → GlobalProjectionStore (gates ingestion)
```

---

### Issue 4.1 — PolicySelectorService

- **File:** `k1/fabric/policy/selector.py`
- **Design:** Evaluates connector policy declarations against the current actor, operation, and safety context. Produces a `PolicyBundle` that gates what Back can do. Lives alongside existing `PolicyEngine` (which is about provider selection — this is about execution authority).
- **Input:** `ResourceUniverse` (candidates with connector_ids) + `intent_types: list[ResolvedIntentType]` + `actor_role: str` + `safety_band: str` + `GlobalProjectionStore` (to read connector policy_declarations)
- **Output:** `PolicyBundle` with `policy_verdict` and gating details.

  ```python
  @dataclass(frozen=True)
  class PolicyBundle:
      policy_id: str
      connector_ids: list[str]
      intent_types: list[ResolvedIntentType]  # typed intents being gated
      actor_role: str
      safety_band: str
      roles_allowed: dict[str, list[str]]     # connector_id → allowed roles
      gates: list[PolicyGate]
      hil_triggers: list[dict]                # conditions that force HIL
      protected_read_policy: dict | None      # protected resource patterns
      guide_refs: list[str]                   # guide card ids to inject
      verifier_requirements: dict[str, str]   # capability_name → verifier method
      policy_verdict: str                     # 'allow' | 'deny' | 'needs_hil' | 'allow_with_gate'
      deny_reason: str | None
      safety_mapping_evidence: dict | None

  @dataclass(frozen=True)
  class PolicyGate:
      gate_id: str
      gate_type: str                   # 'role_check' | 'safety_band' | 'protected_read' | 'hil_trigger'
      description: str
      condition: dict
      action_required: str             # 'allow' | 'deny' | 'ask_hil'

  class PolicySelectorService:
      def __init__(self, global_store: GlobalProjectionStore): ...

      def select(self, universe: ResourceUniverse, intent_types: list[ResolvedIntentType],
                 actor_role: str, safety_band: str) -> PolicyBundle:
          """For each candidate in the universe + each typed intent, load its connector's
          policy_declarations from GlobalProjectionStore. Evaluate:
          1. write_requires_actor_role — is this role allowed to write?
             Gate on intent_types with invocation_mode='execute' + effect='write'.
          2. read_allowed_roles — is this role allowed to read?
             Gate on intent_types with invocation_mode='read'.
          3. protected_resources — does this resource match a protected pattern?
          4. hil_triggers — does any trigger condition match the typed intent?
          5. safety_band — is the actor's band >= the operation's required band?

          Policy gates on typed intent fields (resource_family, operation_family, effect, role),
          not loose operation strings. This ensures policy is enforced against the same
          typed resolution that the CapabilityTypeResolver produced.

          Default-allow: empty role lists → allow all.
          Skip missing connectors: if a candidate's connector_id is not in the store, skip.
          Verdict precedence (worst wins): deny > needs_hil > allow_with_gate > allow.
          """
  ```

- **Key behaviors (proven by POC):**
  - **Default-allow:** `write_requires_actor_role: []` → any role can write.
  - **Missing connector skip:** `get_connector(candidate.connector_id)` returns None → skip (no false denies).
  - **Safety band comparison:** `SAFETY_RANK[actor_band] >= SAFETY_RANK[required_band]` → pass.
  - **Protected read gating:** Resources matching protected patterns require the specified role even for reads.
- **Tests:** GAP-P1-002 — 8 test classes (happy path, deny role, deny band, HIL trigger, protected read, default-allow, missing connector skip, verdict precedence)

### Issue 4.2 — VerificationPlanRunner

- **File:** `k1/fabric/verification/runner.py`
- **Design:** Post-write verification. After `CapabilityFabric` executes a write, the runner builds a plan from the connector's constitution and runs it against the native provider. `submit_result(completed)` requires a passing verification observation.
- **Input:** `CapabilityBinding` + `InvocationObservation` + constitution + `GlobalProjectionStore` + `NativeProviderDispatch`
- **Output:** `VerificationObservation` (verified | degraded_verified | failed | inconclusive | skipped_by_policy | unavailable)

  ```python
  @dataclass(frozen=True)
  class VerificationPlan:
      verification_plan_id: str
      resolution_id: str
      binding_id: str
      invocation_id: str
      verifier_ref: str | None
      verifier_method: str              # 'read_after_write' | 'output_schema' | 'state_compare' | 'none_available'
      expected_effect: str
      expected_resource_state: dict
      readback_capability_ref: str | None
      readback_params: dict | None
      max_staleness_ms: int = 300_000
      degraded_completion_policy: str | None
      required_for_submit_status: str

  @dataclass(frozen=True)
  class VerificationObservation:
      verification_id: str
      verification_plan_id: str
      status: str
      observed_effect: str | None
      observed_resource_state_ref: str | None
      mismatch_summary: str | None
      degraded_reason: str | None
      recovery_directive: dict | None
      proof_refs: list[str]

  class VerificationPlanRunner:
      def __init__(self, native_provider: NativeProviderDispatch, global_store: GlobalProjectionStore,
                   constitution_loader: ConstitutionLoader): ...

      def build_plan(self, binding: CapabilityBinding, observation: InvocationObservation,
                     constitution: ConstitutionArtifact | None, *,
                     degraded_completion_policy: str | None = None) -> VerificationPlan:
          """Read constitution.verification_requirements for this operation.
          Build a plan with the appropriate verifier method and readback parameters.

          The constitution is loaded by the caller via ConstitutionLoader.load(binding.connector_id).
          This method receives the typed ConstitutionArtifact, never a raw ConstitutionRecord."""

      def run(self, plan: VerificationPlan, observation: InvocationObservation | None = None) -> VerificationObservation:
          """Execute the plan. read_after_write: dispatch readback → compare.
          output_schema: validate structured_result against output schema.
          state_compare: deferred. none_available: return skipped_by_policy."""
  ```

- **Key behaviors (proven by POC):**
  - **read_after_write:** Reads back the created resource. Match → `verified`. Mismatch → `failed`.
  - **output_schema:** Validates `observation.structured_result` against the capability's output schema.
  - **Degraded completion:** Policy permits → failed → `degraded_verified`.
  - **No constitution:** No verification requirements → `skipped_by_policy`.
- **Tests:** GAP-P1-006 — 7 test classes (build plan, read_after_write success, mismatch, provider unavailable, output_schema, degraded completion, no constitution)

### Issue 4.3 — ManifestAdmissionService

- **File:** `k1/fabric/manifest_admission.py`
- **Design:** The ingestion gate. Takes a `ConnectorDefinition` (from Epic 2), validates it, and writes it into `GlobalProjectionStore`. This is the ONLY path for connectors to enter the store.
- **Input:** `ConnectorDefinition` (typed, Epic 2) + `GlobalProjectionStore`
- **Output:** `ManifestAdmissionRecord`

  ```python
  @dataclass(frozen=True)
  class ManifestAdmissionRecord:
      manifest_id: str
      connector_id: str
      admission_verdict: str           # 'admitted' | 'rejected'
      record_type: str
      capabilities_admitted_count: int
      capabilities_rejected_count: int
      reason: str | None
      admitted_at: str

  class ManifestAdmissionService:
      def __init__(self, store: GlobalProjectionStore): ...

      def admit(self, definition: ConnectorDefinition) -> ManifestAdmissionRecord:
          """Validate the definition, then write connector + capabilities +
          constitution + resource_kinds + ontology into GlobalProjectionStore."""

      def admit_all(self, definitions: list[ConnectorDefinition]) -> list[ManifestAdmissionRecord]:
          """Admit a batch. Each independently validated. FTS5 rebuilt once at end."""

      # ── Validation ──
      def _validate_connector(self, d: ConnectorDefinition) -> list[str]:
          """14 required fields present and non-empty."""

      def _validate_capability(self, c: CapabilityDefinition) -> list[str]:
          """10 required fields, naming convention, unique name."""

      # ── Ingestion (private) ──
      def _ingest_connector(self, d: ConnectorDefinition) -> None: ...
      def _ingest_capabilities(self, d: ConnectorDefinition) -> int: ...
      def _ingest_constitution(self, d: ConnectorDefinition) -> None: ...
      def _ingest_resource_kinds(self, d: ConnectorDefinition) -> None: ...
      def _ingest_ontology(self, d: ConnectorDefinition) -> None: ...
  ```

- **Key behaviors:**
  - **Idempotent:** `upsert_connector` + `upsert_capability` use ON CONFLICT DO UPDATE.
  - **FTS5 rebuild:** `admit_all()` calls `rebuild_fts_index()` once after batch, not per connector.
  - **Rejection is explicit:** Missing required fields → `admission_verdict='rejected'`, connector NOT written.
  - **Partial batch failure:** One bad connector doesn't block the rest.
- **Tests:** GAP-P1-019 — 8 test classes (valid admit, missing fields reject, batch admit, partial failure, idempotent, with constitution, with ontology, read-only connector)

---

### System Coherence: Epic 1→2→3→4

```
Epic 1 (Stores)    GlobalProjectionStore                   ← written by Epic 4.3 ingestion
Epic 2 (Defs)      ConnectorDefinition                      → input to Epic 4.3
                   build_domain_corpus()                    → generates definitions for Epic 4.3
Epic 3 (Inputs)    ResourceUniverse                         → consumed by Epic 4.1 PolicySelector
                   RequestFrame                             → carries hints used by resolver
Epic 4 (Govern)    PolicySelectorService.select()           ← reads store (Epic 1) + universe (Epic 3) + typed intents (Epic 3.5)
                   PolicyBundle.policy_verdict              ← gates Epic 6 ResolveSituationService
                   VerificationPlanRunner.run()             ← reads store (Epic 1) + binding (Epic 6)
                   VerificationObservation.status           ← gates Epic 6 submit_result
                   ManifestAdmissionService.admit()         ← reads definitions (Epic 2) → writes store (Epic 1)
```

---

## Epic 5: Constitution Infrastructure — Schema & Loader

**Goal:** Build the validation and loading layer for connector constitutions. This is the bridge between how constitutions are DECLARED (Epic 2 `ConstitutionDefinition`), how they are STORED (Epic 1 `ConstitutionRecord`), and how they are USED by the resolver (Epic 6) and verifier (Epic 4.2).

**System context:**

```
ConnectorDefinition.constitution (Epic 2)
  → validated by ConstitutionArtifact schema (Epic 5.1)
  → ingested by ManifestAdmissionService._ingest_constitution() (Epic 4.3)
  → stored as ConstitutionRecord in connector_constitutions table (Epic 1)
  → loaded by ConstitutionLoader (Epic 5.2)
  → consumed by VerificationPlanRunner.build_plan() (Epic 4.2)
  → consumed by ResolveSituationService (Epic 6) for prerequisite_reads, conflict_analysis, HIL gates
```

**Why these are net-new:** The POC has constitution data flowing through dicts with no validation. Epic 5 provides typed validation and a clean loading API that the rest of the system depends on.

---

### Issue 5.1 — ConstitutionArtifact: JSON Schema & Validation

- **File:** `k1/fabric/constitution/schema.py`
- **Design:** Defines the valid shape of a connector constitution. This is the single source of truth that `ConstitutionDefinition` (Epic 2), `ConstitutionRecord` (Epic 1), and all consumers reference. Every constitution flowing through the system must pass this schema.
- **What it validates:**
  - **Structural:** Required identity fields (`connector_id`, `constitution_id`, `schema_version`, `execution_phases`) are present and non-empty. Optional list fields (`prerequisite_reads`, `conflict_analysis_rules`, `companion_resource_roles`, `hil_gates`, `mutation_sequencing`, `verification_requirements`) default to `[]`. Optional summary fields (`precondition_summary`, `companion_resource_summary`, `hil_trigger_summary`, `degradation_policy`, `authored_by`, `authored_at`, `last_proven_at`) default to `None`. If present, all fields must have correct types per JSON Schema.
  - **Semantic:** `prerequisite_reads[].operation` references a declared `execution_phase`. `conflict_analysis_rules[].with_resource_kinds` references known resource kinds. `hil_gates[].trigger` uses valid trigger types. `verification_requirements[].method` uses valid verifier methods.

  ```python
  @dataclass(frozen=True)
  class ConstitutionArtifact:
      """Validated connector constitution. This is the canonical shape every
      constitution must conform to before entering the system."""
      connector_id: str
      constitution_id: str              # "{connector_id}.v1"
      schema_version: str               # semver, e.g. "1.0.0"
      authored_by: str | None
      authored_at: str | None
      last_proven_at: str | None
      execution_phases: list[str]       # "read", "mutate"
      prerequisite_reads: list[PrerequisiteRead]
      conflict_analysis_rules: list[ConflictRule]
      companion_resource_roles: list[CompanionResourceRole]
      hil_gates: list[HILGate]
      mutation_sequencing: list[MutationStep]
      verification_requirements: list[VerificationRequirement]
      precondition_summary: str | None
      companion_resource_summary: str | None
      hil_trigger_summary: str | None
      degradation_policy: str | None

  @dataclass(frozen=True)
  class PrerequisiteRead:
      operation: str                     # "list", "search"
      resource_kind: str                 # "calendar_event"
      reason: str                        # human-readable explanation
      required: bool = True
      timeout_ms: int = 5000

  @dataclass(frozen=True)
  class ConflictRule:
      check: str                         # "time_overlap", "participant_availability", "duplicate"
      with_resource_kinds: list[str] = field(default_factory=list)
      description: str = ""

  @dataclass(frozen=True)
  class CompanionResourceRole:
      resource_kind: str
      role: str                          # "conflict_source", "dependency", "impacted_member"
      description: str = ""

  @dataclass(frozen=True)
  class HILGate:
      trigger: str                       # "missing_required_field", "time_conflict_detected", "ambiguous_person"
      field: str | None = None           # for missing_required_field trigger
      prompt: str
      options: list[str] = field(default_factory=list)

  @dataclass(frozen=True)
  class MutationStep:
      order: int
      phase: str                         # which execution_phase this step belongs to: 'read' | 'mutate'
      operation: str                     # which capability action_name to invoke: 'list' | 'create' | 'update' | 'delete'
      description: str = ""

  @dataclass(frozen=True)
  class VerificationRequirement:
      method: str                        # "read_after_write", "output_schema", "state_compare"
      description: str = ""
      required_for_submit: bool = False

  # ── JSON Schema (Draft-07) ──
  CONSTITUTION_JSON_SCHEMA: dict = {
      "$schema": "https://json-schema.org/draft-07/schema#",
      "type": "object",
      "additionalProperties": False,
      "required": ["connector_id", "constitution_id", "schema_version", "execution_phases"],
      "properties": {
          "connector_id": {"type": "string", "pattern": "^[a-z]+\\.[a-z][a-z0-9_]*$"},
          "constitution_id": {"type": "string"},
          "schema_version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
          "authored_by": {"type": ["string", "null"]},
          "authored_at": {"type": ["string", "null"]},
          "last_proven_at": {"type": ["string", "null"]},
          "execution_phases": {"type": "array", "items": {"type": "string"}, "minItems": 1},
          "prerequisite_reads": {"type": "array", "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["operation", "resource_kind", "reason"],
              "properties": {
                  "operation": {"type": "string"}, "resource_kind": {"type": "string"},
                  "reason": {"type": "string"}, "required": {"type": "boolean"},
                  "timeout_ms": {"type": "integer", "minimum": 1000}
              }
          }},
          "conflict_analysis_rules": {"type": "array", "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["check"],
              "properties": {"check": {"type": "string"}, "with_resource_kinds": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}}
          }},
          "hil_gates": {"type": "array", "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["trigger", "prompt"],
              "properties": {"trigger": {"type": "string"}, "field": {"type": ["string", "null"]}, "prompt": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}}
          }},
          "verification_requirements": {"type": "array", "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["method"],
              "properties": {"method": {"type": "string"}, "description": {"type": "string"}, "required_for_submit": {"type": "boolean"}}
          }},
          "mutation_sequencing": {"type": "array", "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["order", "phase", "operation"],
              "properties": {"order": {"type": "integer"}, "phase": {"type": "string"}, "operation": {"type": "string"}, "description": {"type": "string"}}
          }},
          "companion_resource_roles": {"type": "array", "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["resource_kind", "role"],
              "properties": {"resource_kind": {"type": "string"}, "role": {"type": "string"}, "description": {"type": "string"}}
          }},
          "precondition_summary": {"type": ["string", "null"]},
          "companion_resource_summary": {"type": ["string", "null"]},
          "hil_trigger_summary": {"type": ["string", "null"]},
          "degradation_policy": {"type": ["string", "null"]},
      }
  }

  def validate_constitution(data: dict) -> ConstitutionArtifact:
      """Validate a raw dict against CONSTITUTION_JSON_SCHEMA.
      On pass, parse into ConstitutionArtifact with nested sub-types.
      On fail, raise ConstitutionValidationError with field-level detail."""

  def validate_constitution_semantics(artifact: ConstitutionArtifact, known_resource_kinds: set[str]) -> list[str]:
      """Semantic rules beyond JSON Schema:
      - prerequisite_reads[].resource_kind must be in known_resource_kinds
      - conflict_analysis_rules[].with_resource_kinds[] must be in known_resource_kinds
      - companion_resource_roles[].resource_kind must be in known_resource_kinds
      - mutation_sequencing[].phase must match a declared execution_phase
      - mutation_sequencing[].operation must match a declared capability action_name / operation_family
      - verification_requirements[].method must be a known verifier method
      Returns list of violation messages (empty = valid)."""
  ```

- **Key design:**
  - **Typed sub-dataclasses:** `PrerequisiteRead`, `ConflictRule`, `CompanionResourceRole`, `HILGate`, `MutationStep`, `VerificationRequirement` — not raw dicts. This makes consumers type-safe.
  - **Two-phase validation:** JSON Schema (structural) → semantic rules (references must resolve). Structural runs at ingestion. Semantic runs at load time when `known_resource_kinds` are available.
  - **Error granularity:** Validation failures cite the exact field path and reason, e.g. `"prerequisite_reads[0].resource_kind: 'unknown_type' not in known resource kinds"`.
  - **Coherence with Epic 2:** `ConstitutionDefinition` (a loose dataclass for authoring) → `ConstitutionArtifact` (a validated, typed object) via `validate_constitution()`. The definition is what authors write; the artifact is what the system trusts.
- **Tests:** GAP-P1-008 — `tests/k1/fabric/constitution/test_constitution_schema.py`
  - `TestStructuralValidation` (8 tests): valid full constitution, missing connector_id, missing execution_phases, wrong type (prerequisite_reads as string), schema_version not semver, timeout_ms below minimum, empty execution_phases, extra unknown field
  - `TestSemanticValidation` (6 tests): all resource_kinds valid, one unknown resource_kind, mutation_step references undeclared phase, verifier_method unknown, empty known_resource_kinds → all fail, multiple violations returned
  - `TestSubTypeRoundtrip` (4 tests): PrerequisiteRead from/to dict, HILGate with options, MutationStep ordering, VerificationRequirement with required_for_submit
  - `TestCoherence` (3 tests): ConstitutionDefinition → dict → validate → ConstitutionArtifact (roundtrip), ConstitutionRecord from store → validate → artifact, artifact → dict → back (idempotent)

### Issue 5.2 — ConstitutionLoader

- **File:** `k1/fabric/constitution/loader.py`
- **Design:** Loads constitutions from `GlobalProjectionStore.connector_constitutions` table, deserializes JSON columns, validates against `ConstitutionArtifact` schema, and returns typed artifacts. This is the single entry point for reading constitutions — no consumer reads the store directly.
- **Dependencies:** `GlobalProjectionStore` + `ConstitutionArtifact` + `validate_constitution()` + `validate_constitution_semantics()`

  ```python
  class ConstitutionLoader:
      def __init__(self, global_store: GlobalProjectionStore): ...

      def load(self, connector_id: str, *,
               known_resource_kinds: set[str] | None = None) -> ConstitutionArtifact | None:
          """Load a single connector's constitution. Returns None if not found.
          If known_resource_kinds is provided, runs semantic validation.
          Raises ConstitutionValidationError if the stored data fails validation."""

      def load_all(self, *,
                   known_resource_kinds: set[str] | None = None) -> list[ConstitutionArtifact]:
          """Load all constitutions. Skips connectors with missing or invalid
          constitutions (logs warning, continues)."""

      def get_prerequisite_reads(self, connector_id: str) -> list[PrerequisiteRead]:
          """Convenience: return just the prerequisite_reads for a connector.
          Returns empty list if no constitution or no prerequisite reads."""

      def get_verification_requirements(self, connector_id: str) -> list[VerificationRequirement]:
          """Convenience: return just the verification_requirements for a connector.
          Returns empty list if no constitution or no verification requirements."""

      def get_hil_gates(self, connector_id: str) -> list[HILGate]:
          """Convenience: return just the hil_gates for a connector."""

      def get_conflict_rules(self, connector_id: str) -> list[ConflictRule]:
          """Convenience: return just the conflict_analysis_rules for a connector."""

      def get_mutation_sequence(self, connector_id: str) -> list[MutationStep]:
          """Convenience: return just the mutation_sequencing, sorted by order."""

      # ── Internal ──
      def _row_to_artifact(self, row: sqlite3.Row) -> ConstitutionArtifact:
          """Deserialize all *_json columns from a connector_constitutions row,
          build a dict, validate, and return ConstitutionArtifact."""

      def _load_raw(self, connector_id: str) -> dict | None:
          """Load the raw row from the store as a dict, without validation.
          Returns None if not found."""
  ```

- **Key design:**
  - **Single entry point:** All consumers (VerificationPlanRunner, ResolveSituationService, PromptPackBuilder) call `ConstitutionLoader`, not `GlobalProjectionStore.get_constitution()` directly. This ensures validation happens once, at load time.
  - **Lazy semantic validation:** `known_resource_kinds` is optional. Structural validation always runs. Semantic validation runs when the caller provides the set of known resource kinds (typically from the domain catalog).
  - **Convenience methods:** `get_prerequisite_reads()`, `get_verification_requirements()`, etc. avoid forcing every consumer to navigate the full artifact.
  - **Graceful degradation:** `load_all()` skips invalid constitutions rather than failing. A corrupted constitution for one connector shouldn't block the entire system.
  - **Coherence with Epic 4.2:** `VerificationPlanRunner.build_plan()` calls `loader.get_verification_requirements(connector_id)` to get the verifier method. Clean, typed return.
  - **Coherence with Epic 6:** `ResolveSituationService` calls `loader.load(connector_id, known_resource_kinds=...)` to enforce prerequisite_reads, conflict_analysis_rules, and HIL gates during the verdict cascade.
- **Tests:** Included in GAP-P1-008 — `TestConstitutionLoader` (8 tests)
  - Load existing → returns ConstitutionArtifact with all sub-types populated
  - Load missing → returns None (no exception)
  - Load with semantic validation → passes when all resource_kinds known
  - Load with semantic validation → raises when unknown resource_kind referenced
  - Load after upsert → sees updated data (not cached)
  - Load all → returns 3 artifacts, skips 1 with invalid JSON
  - Convenience methods: get_prerequisite_reads, get_verification_requirements, get_hil_gates all return correct sub-types
  - JSON roundtrip: store → load → serialize → identical dict

- **Run:** `pytest tests/k1/fabric/constitution/test_constitution_schema.py -v`

---

### System Coherence: Epic 1→2→3→4→5

```
Epic 1 (Stores)    ConstitutionRecord in connector_constitutions table
                   ↑ written by Epic 4.3 _ingest_constitution()
                   ↓ read by Epic 5.2 ConstitutionLoader._load_raw()

Epic 2 (Defs)      ConstitutionDefinition (loose, for authoring)
                   → validated by Epic 5.1 validate_constitution()
                   → becomes ConstitutionArtifact (typed, trusted)

Epic 3 (Inputs)    [no direct constitution involvement]

Epic 4 (Govern)    ManifestAdmissionService._ingest_constitution()
                     validates via Epic 5.1 before writing to Epic 1
                   VerificationPlanRunner.build_plan()
                     reads via Epic 5.2 get_verification_requirements()

Epic 5 (Const)     ConstitutionArtifact + sub-types (the validated shape)
                   ConstitutionLoader (the single read path)
                   ↓ consumed by Epic 4.2 (verifier) and Epic 6 (resolver)

Epic 6 (Orch)      ResolveSituationService
                     reads via Epic 5.2 loader.load()
                     enforces prerequisite_reads, conflict_analysis_rules,
                     hil_gates, mutation_sequencing from constitution
```

---

## Epic 6: Orchestration — CapabilityBinder, SituatedResolver, PromptPackBuilder

**Goal:** Build the three orchestration components that tie Epics 1–5 together into a working resolution pipeline. These are the runtime engine of the Fabric.

**Design derivation from Epics 1–5:**

| Epic | What It Provides | How Epic 6 Consumes It |
|------|-----------------|------------------------|
| 1 (Stores) | `GlobalProjectionStore` — typed capability/connector/graph lookup | Binder: Pass 1 (typed) reads `capability_type_index`, Pass 2 (exact) reads `find_capabilities()`, Pass 3 (BM25) reads `search_capabilities()`. PromptPackBuilder reads `get_connector()`, `get_capability()`. |
| 1 (Stores) | `LocalProjectionStore` — per-session connected resources, household members, alias index | Binder: skips stale candidates, reads `connected_resources` for freshness. SituatedResolver: resolves person refs via `resolve_alias()`. |
| 1 (Stores) | `IdempotencyStore` — enforces no-duplicate execution | SituatedResolver: verdict step 2 checks `check(idempotency_key)` before binding. |
| 2 (Defs) | `ConnectorDefinition`, `CapabilityDefinition` — the declared shape of every connector | PromptPackBuilder: guide cards, schema cards, constitution cards all sourced from definitions ingested via Epics 4.3+5. |
| 3 (Inputs) | `RequestFrame`, `RequestFrameIntent`, `ResourceUniverse`, `ResolvedIntentType` | Binder: `bind()` takes `ResolvedIntentType` list (with `domain`, `resource_family`, `operation_family`, `effect`, `role`), `ResourceUniverse` (with candidates), `PolicyBundle`. SituatedResolver: `resolve()` takes `RequestFrame`. |
| 4 (Govern) | `PolicyBundle` — gates what Back can do | Binder: skips denied candidates, marks `unbound_roles` with `policy_block` reason. SituatedResolver: verdict step 8 checks `policy_verdict`. |
| 4 (Govern) | `VerificationPlanRunner` — post-write verification | Not consumed directly by Epic 6 (verification runs AFTER capability execution). Binder tags primary write bindings with `verifier_ref`. |
| 5 (Const) | `ConstitutionArtifact` — typed constitution with `prerequisite_reads`, `hil_gates`, `conflict_analysis_rules`, `mutation_sequencing`, `verification_requirements` | Binder: reads `prerequisite_reads` to discover prerequisite bindings, reads `companion_resource_roles` to discover companion bindings. SituatedResolver: verdict steps 10–12 load constitution, enforce prerequisites + HIL gates + conflict rules. PromptPackBuilder: builds `ConstitutionCard` from `ConstitutionArtifact` (typed, not raw dicts). |
| 5 (Const) | `ConstitutionLoader` — single read path for constitutions | SituatedResolver calls `loader.load(connector_id, known_resource_kinds=...)`. PromptPackBuilder calls `loader.get_prerequisite_reads()`, `loader.get_hil_gates()`. |

**POC role:** Reference implementation for technique — how 3-pass discovery works, how `commit_tool_selection()` validates Phase 2 choices, how 5 disclosure phases gate prompt visibility, how redaction leak detection prevents secret markers from reaching the LLM. The POC proves these patterns work. The whiteboard defines the API. We build the whiteboard API clean.

---

### Issue 6.1 — CapabilityBinderService: Types & 3-Pass Discovery

- **File:** `k1/fabric/resolver/capability_binder.py`
- **Design:** Takes resolved intent types + resource universe + policy bundle, performs 3-pass discovery against `GlobalProjectionStore` to produce a `BindingBundle`. This is the component that answers "WHAT capabilities can fulfill this intent, on THIS resource, for THIS actor?"

**Key design decisions (derived from Epics 1–5):**

1. **Pass 1 uses typed graph results, not keyword heuristics.** Epic 3.3 removed `OPERATION_KEYWORDS` / `RESOURCE_KIND_KEYWORDS` from Fabric. The binder's Pass 1 reads `ResolvedIntentType.fallback_capabilities` — these are deterministic results from `capability_type_index` (the graph ontology table populated in Epic 1.2). No guessing. If the graph resolver found `tool.execute.family.calendar.create` at high confidence, the binder uses it directly.

2. **Pass 2 uses `invocation_mode` + `effect`, not `operation`.** Epic 1.2 renamed the column from `operation` to `invocation_mode` and added `action_name`. Pass 2 queries `find_capabilities(resource_kind=..., invocation_mode=..., effect=..., connector_id=...)`. The old POC concept of "operation" as a combined `read`/`execute` + verb is split into `invocation_mode` (`read` | `execute`) + `action_name` (`list` | `create` | `update` | ...).

3. **Pass 3 uses BM25 FTS5 with the action text as query.** When typed + exact both fail, the LLM's original action text (`RequestFrameIntent.action`) is used as the BM25 query against `capabilities_fts`. This is the fuzzy fallback.

4. **Role propagation.** `ResolvedIntentType.role` (from graph resolver's `resource_connector_edges.role`) flows into `CapabilityBinding.role`. The binder also discovers companion/prerequisite/verifier bindings from the constitution (loaded via `ConstitutionLoader`, Epic 5.2).

5. **Policy gating.** Candidates blocked by policy → `unbound_roles` with `policy_block` reason. Stale candidates on write operations → `unbound_roles` with `stale_projection` reason. The binder does NOT filter these — it reports them so the SituatedResolver can produce the correct verdict.

6. **Deduplication.** Bindings for the same `(connector_id, capability_name, resource_id, actor_id, session_id)` are deduplicated via SHA-256 binding IDs. This prevents duplicate bindings when multiple intents resolve to the same capability on the same resource.

**Dataclasses:**

  ```python
  @dataclass(frozen=True)
  class CapabilityBinding:
      """One bound capability with full context for Back's LLM."""
      binding_id: str                      # SHA-256(connector_id:cap_name:resource_id:actor_id:session_id)
      capability_name: str                 # "tool.execute.family.calendar.create"
      connector_id: str                    # "family.calendar"
      invocation_mode: str                 # 'read' | 'execute'
      action_name: str                     # 'list' | 'search' | 'create' | 'update' | 'delete' | 'send'
      effect: str                          # 'read' | 'write' | 'delete' | 'compute'
      resource_kind: str                   # "calendar_event"
      resource_id: str                     # resolved resource identifier from LocalProjectionStore
      role: str                            # 'primary' | 'companion' | 'prerequisite' | 'verifier'
      confidence: str                      # 'high' | 'medium' | 'low' — from ResolvedIntentType
      source: str                          # 'typed_intent' | 'exact_match' | 'bm25_search'
      input_schema_ref: str | None         # JSON Schema ref from CapabilityRecord
      output_schema_ref: str | None
      effect_summary: str                  # capability description for LLM
      safety_requirement: str              # 'GREEN' | 'AMBER' | 'RED'
      authority_verdict: str               # 'bound' | 'pending' | 'blocked'
      verifier_ref: str | None             # set for primary_write bindings
      guide_refs: list[str]                # guide card IDs to inject
      freshness_state: str                 # 'fresh' | 'stale' | 'unknown'
      limitations: list[str]               # known limitations of this binding
      created_at: str
      expires_at: str                      # 5-min TTL

  @dataclass(frozen=True)
  class UnboundRole:
      """A role that could not be filled — why binding failed for a candidate."""
      invocation_mode: str                 # 'read' | 'execute'
      action_name: str
      resource_kind: str
      reason: str                          # 'policy_block' | 'stale_projection' | 'missing_capability' | 'missing_connector' | 'guide_only'
      detail: str                          # connector_id or policy deny_reason

  @dataclass(frozen=True)
  class BindingBundle:
      """Complete set of bound capabilities for a resolution.
      Separated by role so Back can reason about execution order."""
      bundle_id: str
      resolution_id: str
      primary: CapabilityBinding | None    # the main capability to execute
      companions: list[CapabilityBinding]  # companion resources (from constitution.companion_resource_roles)
      prerequisites: list[CapabilityBinding]  # prerequisite reads (from constitution.prerequisite_reads)
      verifiers: list[CapabilityBinding]   # post-write verification capabilities
      alternatives: list[CapabilityBinding]  # alternative bindings (different connectors, same intent)
      unbound_roles: list[UnboundRole]     # roles that could NOT be filled
      tool_name_cards: list[dict]          # {name, description, role} for LLM tool selection
      selected_schema_cards: list[dict]    # schemas for committed tools (schema_binding phase only)
      guide_refs: list[str]                # aggregated guide card IDs
      verifier_links: list[dict]           # {capability_name, connector_id, verification} for verifier
      binding_diagnostics: list[str]       # human-readable diagnostics
      disclosure_phase: str                # which phase this bundle was built for

      @property
      def all_bindings(self) -> list[CapabilityBinding]:
          """Flat list for iteration. Ordered: primary → prerequisites → companions → verifiers → alternatives."""
          result = []
          if self.primary: result.append(self.primary)
          result.extend(self.prerequisites)
          result.extend(self.companions)
          result.extend(self.verifiers)
          result.extend(self.alternatives)
          return result

      @property
      def allowed_capability_names(self) -> list[str]:
          """Capability names that Back is authorized to invoke."""
          return [b.capability_name for b in self.all_bindings if b.authority_verdict == "bound"]

  @dataclass(frozen=True)
  class ToolSelectionCommit:
      """Post-selection commit — validates Back's chosen tools against the Phase 1 bundle."""
      committed_tool_names: list[str]      # tools Back selected that are valid
      rejected_tool_names: list[str]       # tools Back selected that are NOT in the bundle
      accepted: bool                       # True iff all committed tools are valid
      reason: str | None                   # explanation when not accepted
  ```

**API:**

  ```python
  class CapabilityBinderService:
      def __init__(self, global_store: GlobalProjectionStore, local_store: LocalProjectionStore): ...

      def bind(self,
               resolved_intents: list[ResolvedIntentType],
               resource_universe: ResourceUniverse,
               policy_bundle: PolicyBundle,
               *,
               actor_id: str,
               session_id: str,
               disclosure_phase: str = "connector_summary",
               committed_tool_names: list[str] | None = None,
               intent_actions: list[str] | None = None,
               constitution_loader: ConstitutionLoader | None = None,
               ) -> BindingBundle:
          """3-pass discovery for every intent × candidate pair.

          Pass 1 — Typed intent (graph-resolved):
            For each ResolvedIntentType with confidence ≥ 'low':
              Read intent.fallback_capabilities (from capability_type_index).
              Filter by connector match + effect match.
              Enrich each with full CapabilityRecord from store.
              → source='typed_intent', confidence from ResolvedIntentType.

          Pass 2 — Exact match (structured query):
            Query find_capabilities(resource_kind, invocation_mode, effect, connector_id).
            Match invocation_mode from UNIVERSAL_OPERATION_ALIASES mapping.
            → source='exact_match', confidence='high'.

          Pass 3 — BM25 FTS5 (semantic fallback):
            Query search_capabilities(query=action_text, top_k=10).
            Filter by connector_id if available.
            → source='bm25_search', confidence='medium'.

          After binding primary:
            - Load constitution via constitution_loader (Epic 5.2).
            - Discover prerequisites from constitution.prerequisite_reads.
            - Discover companions from constitution.companion_resource_roles.
            - Tag primary_write with verifier_ref.
            - Deduplicate by (connector_id, capability_name, resource_id, actor_id, session_id).

          Policy gates (applied before binding):
            - policy_verdict == 'deny' → UnboundRole(reason='policy_block').
            - freshness_state == 'stale' + write intent → UnboundRole(reason='stale_projection').
            - No matches after all 3 passes → UnboundRole(reason='missing_capability').
          """

      def commit_tool_selection(self,
                                binding_bundle: BindingBundle,
                                committed_tool_names: list[str],
                                ) -> ToolSelectionCommit:
          """Phase 2 gate: validate that every committed tool name exists in the Phase 1 bundle.
          Returns ToolSelectionCommit with accepted/rejected breakdown.
          Reason text includes the list of valid tool names when rejected."""

      def refresh_binding(self, binding_id: str) -> CapabilityBinding:
          """Refresh a binding's TTL. Raises KeyError if binding not found."""
  ```

**Internal helpers (proven by POC, now typed):**

  ```python
  def _find_all_capabilities(
      store: GlobalProjectionStore,
      candidate: ResourceCandidate,
      invocation_mode: str,                # 'read' | 'execute' (not 'list'/'create')
      effect: str,                         # 'read' | 'write' | 'delete' | 'compute'
      *,
      action_text: str = "",               # for BM25 fallback
      typed_intent: ResolvedIntentType | None = None,
  ) -> list[CapabilityRecord]:
      """3-pass discovery returning typed CapabilityRecord objects."""

  def _make_binding(
      capability: CapabilityRecord,
      candidate: ResourceCandidate,
      actor_id: str,
      session_id: str,
      *,
      role: str,
      source: str,
      confidence: str,
  ) -> CapabilityBinding:
      """Construct a CapabilityBinding from a CapabilityRecord + context."""

  def _dedupe_bindings(bindings: list[CapabilityBinding]) -> list[CapabilityBinding]:
      """Deduplicate by binding_id. Keep first occurrence, preserve order."""

  # Universal mapping from action verbs → (invocation_mode, effect)
  UNIVERSAL_ACTION_MAP: dict[str, tuple[str, str]] = {
      "list": ("read", "read"),    "search": ("read", "read"),
      "create": ("execute", "write"), "update": ("execute", "write"),
      "delete": ("execute", "delete"), "send": ("execute", "write"),
  }
  ```

- **Coherence check with Epic 3.5:** `ResolvedIntentType.fallback_capabilities` comes from `CapabilityTypeResolver._resolve_one()` step 4 — the `lookup_capability_by_type()` call on `capability_type_index`. The binder does NOT re-derive the type; it trusts the graph resolver's output.
- **Coherence check with Epic 5.2:** The binder calls `constitution_loader.get_prerequisite_reads(connector_id)` (not raw `store.get_constitution()`). This ensures validation has already run on the constitution.
- **Coherence check with Epic 1.3:** `find_capabilities()` on the store uses `invocation_mode` + `effect` columns (not the old `operation` column). The index `idx_capability_lookup` covers `(resource_kind, invocation_mode, effect, connector_id, record_type, safety_band_min)`.
- **Verify:** `python -c "from k1.fabric.resolver.capability_binder import CapabilityBinderService, CapabilityBinding, BindingBundle, UnboundRole, ToolSelectionCommit"`

---

### Issue 6.2 — ResolveSituationService: 13-Step Verdict Cascade

- **File:** `k1/fabric/resolver/situated_resolver.py`
- **Design:** The main orchestrator. Takes a `RequestFrame`, runs the full pipeline through all Epic 3–5 services, and produces a `ResolutionEnvelope` with a verdict. This is THE entry point Back calls.

**Key design decisions (derived from Epics 1–5):**

1. **Single entry point.** Back calls `resolve(request)` and gets a `ResolutionEnvelope`. No intermediate calls, no partial state. The envelope is the complete snapshot of the resolution.

2. **13-step verdict cascade in strict precedence order.** Fast checks first (budget, idempotency — no store reads). Then resource projection. Then graph type resolution. Then policy. Then binding. Then constitution. The order is fixed because later steps depend on outputs of earlier steps.

3. **Constitution enforcement is steps 10–12.** The constitution is loaded ONCE per resolution (from `ConstitutionLoader`, Epic 5.2) after the primary binding is identified. Prerequisite reads, HIL gates, and conflict rules are all derived from the same `ConstitutionArtifact`.

4. **Sub-reason on every non-happy verdict.** `blocked_by_policy` includes WHICH policy gate failed. `can_execute_with_gate` includes WHICH prerequisite read is incomplete. `missing_capability` includes WHICH resource_kind had no binding. This is critical for Back's error recovery.

5. **Tier promotion is data-driven.** `promote_to_tier3` triggers on 6+ distinct connectors OR 3+ dependency depth (prereq→write→verify chains). Not heuristic — derived from the binding bundle structure.

6. **Prompt pack built as part of resolution.** The `ResolutionEnvelope` includes a `PromptPack` so Back doesn't need a separate call. The prompt pack is built with the correct `disclosure_phase` from the request.

**Dataclasses:**

  ```python
  @dataclass(frozen=True)
  class ResolveSituationRequest:
      """What Back sends to initiate resolution."""
      request_id: str
      frame: RequestFrame                   # Epic 3.2 — carries intents, refs, time window, safety context
      actor_id: str
      space_id: str
      session_id: str
      tier: str                             # 'LOW' | 'MEDIUM' | 'HIGH'
      safety_band: str                      # 'GREEN' | 'AMBER' | 'RED'
      disclosure_phase: str                 # 'connector_summary' | 'tool_name_selection' | 'schema_binding' | 'execution'
      freshness_policy: str                 # 'require_fresh' | 'allow_stale_reads'
      prompt_budget_tokens: int = 8000
      completed_prerequisite_bindings: list[str] = field(default_factory=list)  # binding_ids from prior rounds
      previous_resolution_id: str | None = None
      idempotency_keys: list[str] = field(default_factory=list)  # for duplicate detection
      budget_remaining: dict | None = None  # {max_iterations, max_fabric_calls, max_prompt_tokens}

  @dataclass(frozen=True)
  class ResolutionEnvelope:
      """Complete resolution snapshot returned to Back."""
      resolution_id: str
      request_id: str
      request_frame: RequestFrame
      candidate_universe: ResourceUniverse | None   # None if resource resolution failed
      intent_resolutions: list[ResolvedIntentType]  # typed graph results (Epic 3.5)
      policy_bundle: PolicyBundle | None            # None if policy not evaluated
      binding_bundle: BindingBundle | None          # None if binding not performed
      constitution: ConstitutionArtifact | None     # loaded from ConstitutionLoader (Epic 5.2)
      prompt_pack: PromptPack | None                # built by PromptPackBuilder (Issue 6.3)
      verdict: str                                  # see cascade below
      sub_reason: str | None                        # e.g. "prerequisite_read_incomplete: list calendar_event"
      allowed_next_actions: list[str]               # human-readable descriptions
      allowed_capability_names: list[str]            # capability_names Back is authorized to invoke
      capability_name_to_binding: dict[str, str]    # capability_name → binding_id
      hil_request: dict | None                      # populated when verdict == 'needs_hil'
      recovery_directive: dict | None               # populated when verdict == 'stale_projection'
      diagnostics: list[dict]                       # full diagnostic trace
      created_at: str
      expires_at: str                               # 5-min TTL

      def to_dict(self) -> dict: ...
  ```

**API:**

  ```python
  class ResolveSituationService:
      def __init__(self,
                   global_store: GlobalProjectionStore,
                   local_store: LocalProjectionStore,
                   *,
                   resource_resolver: ResolveResourcesService | None = None,
                   type_resolver: CapabilityTypeResolver | None = None,
                   policy_selector: PolicySelectorService | None = None,
                   capability_binder: CapabilityBinderService | None = None,
                   constitution_loader: ConstitutionLoader | None = None,
                   prompt_pack_builder: PromptPackBuilder | None = None,
                   idempotency_store: IdempotencyStore | None = None,
                   ): ...

      def resolve(self, request: ResolveSituationRequest) -> ResolutionEnvelope:
          """Full resolution pipeline. 13-step verdict cascade."""

      # ── Verdict cascade (private) ──
      def _determine_verdict(self,
                             request: ResolveSituationRequest,
                             universe: ResourceUniverse,
                             policy_bundle: PolicyBundle,
                             binding_bundle: BindingBundle,
                             constitution: ConstitutionArtifact | None,
                             diagnostics: list[dict],
                             ) -> tuple[str, str | None]:
          """13-step cascade. First failure wins. Returns (verdict, sub_reason)."""
  ```

**13-step verdict cascade** (order matters — fast checks first, constitution last):

| Step | Check | Verdict on Fail | Sub-Reason | Epic Source |
|------|-------|-----------------|------------|-------------|
| 1 | Budget exhausted? (`max_iterations ≤ 0` or `max_fabric_calls ≤ 0` or `prompt_budget ≤ 1`) | `cannot_execute` | `budget_exhausted:{field}` | ResolveSituationRequest.budget_remaining |
| 2 | Idempotency duplicate? (`idempotency_store.check(key).state == 'succeeded'`) | `cannot_execute` | `idempotency_duplicate:{key}` | Epic 1.6 IdempotencyStore |
| 3 | Ambiguous person reference? (≥2 matches for any person_hint in local_store.resolve_alias) | `needs_disambiguation` | `ambiguous_person:{raw}` | Epic 3.4 LocalProjectionStore |
| 4 | Stale projection on write intent? (any candidate.freshness_state == 'stale' AND write intended) | `stale_projection` | `stale_resource:{resource_id}` | Epic 3.4 ResourceCandidate |
| 5 | Unresolved refs? (any unresolved.reason == 'ambiguous') | `needs_disambiguation` | `ambiguous_resource:{raw}` | Epic 3.4 ResourceUniverse |
| 6 | Unresolved refs? (any unresolved.reason == 'not_found') | `missing_required_params` | `resource_not_found:{raw}` | Epic 3.4 ResourceUniverse |
| 7 | Intent too vague? (write intent with no subject_hint, no params, no time_window) | `missing_required_params` | `intent_too_vague` | Epic 3.2 RequestFrameIntent |
| 8 | Promote to Tier 3? (≥6 distinct connectors OR ≥3 dependency depth OR cross-actor with ≥4 connectors) | `promote_to_tier3` | `connectors:{n}_depth:{d}` | BindingBundle structure |
| 9 | Policy denied? (`policy_bundle.policy_verdict == 'deny'`) | `blocked_by_policy` | `{deny_reason}` | Epic 4.1 PolicyBundle |
| 10 | Stale binding? (any unbound_role.reason == 'stale_projection') | `stale_projection` | `stale_binding:{detail}` | BindingBundle.unbound_roles |
| 11 | Missing capability? (any unbound_role.reason in {'missing_capability','missing_connector','guide_only'}) | `missing_capability` | `{reason}:{resource_kind}` | BindingBundle.unbound_roles |
| 12 | Incomplete prerequisites? (prerequisite binding_ids not in completed_prerequisite_bindings) | `can_execute_with_gate` | `prerequisite_read_incomplete:{cap_name}` | Epic 5.2 ConstitutionArtifact.prerequisite_reads |
| 13 | HIL gate triggered? (constitution.hil_gates trigger matches missing params or conflict detected) | `needs_hil` | `hil_gate:{trigger}` | Epic 5.1 HILGate |

If all 13 steps pass → `can_execute` (no sub_reason).

**Internal helpers (proven by POC, now typed against Epic 1–5 types):**

  ```python
  def _budget_exhausted(request: ResolveSituationRequest) -> bool:
      """Check budget_remaining dict fields against zero."""

  def _has_ambiguous_person_reference(request: ResolveSituationRequest,
                                      local_store: LocalProjectionStore) -> bool:
      """Resolve person_hint from each intent against local_store.resolve_alias().
      >1 match on any person_hint → ambiguous."""

  def _has_stale_write_candidate(frame: RequestFrame, universe: ResourceUniverse) -> bool:
      """Any candidate.freshness_state == 'stale' AND any intent has write invocation_mode."""

  def _intent_too_vague(frame: RequestFrame) -> bool:
      """Write intent with no subject_hint, no params, and no time_window → too vague.
      This is the ONE universal check — everything else is the CapabilityBinder's job."""

  def _should_promote_to_tier3(binding_bundle: BindingBundle) -> tuple[bool, str | None]:
      """Data-driven tier promotion:
      - ≥6 distinct connector_ids across all bindings
      - ≥3 dependency depth (prerequisite → write → verify chain)
      - Cross-actor companion resources with ≥4 connectors
      Returns (should_promote, reason_string)."""

  def _has_incomplete_prerequisites(binding_bundle: BindingBundle,
                                    completed: list[str]) -> bool:
      """Any prerequisite binding whose binding_id is NOT in completed list."""

  def _hil_gate_triggered(constitution: ConstitutionArtifact | None,
                          frame: RequestFrame) -> tuple[bool, str | None]:
      """Check constitution.hil_gates against missing required params in frame.
      Returns (triggered, trigger_description)."""

  def _build_prompt_pack(self, request: ResolveSituationRequest,
                         universe: ResourceUniverse,
                         verdict: str,
                         binding_bundle: BindingBundle) -> PromptPack:
      """Build a lightweight inline PromptPack for the resolution envelope.
      Delegates to PromptPackBuilder for full disclosure-phase builds."""

  def _allowed_next_actions(self, verdict: str,
                            binding_bundle: BindingBundle,
                            completed_prerequisites: list[str]) -> list[dict[str, str]]:
      """Determine what Back is authorized to do next based on verdict."""
  ```

- **Coherence check with Epic 1.6:** Step 2 calls `idempotency_store.check(key)` before any binding happens. The idempotency store's `succeeded` state is immutable — this prevents duplicate execution at the resolution level.
- **Coherence check with Epic 3.2:** The `RequestFrame` carries `operation_hint` and `resource_kind_hint` as EXPLICIT fields populated by Back. The SituatedResolver does NOT derive them — it passes them through to the CapabilityTypeResolver.
- **Coherence check with Epic 5.2:** Constitution is loaded via `constitution_loader.load(connector_id, known_resource_kinds=...)`. The `known_resource_kinds` set comes from the domain catalog (Epic 2.4) — all 50 connectors' resource_kinds across all 5 domains.
- **Verify:** `python -c "from k1.fabric.resolver.situated_resolver import ResolveSituationService, ResolveSituationRequest, ResolutionEnvelope"`

---

### Issue 6.3 — PromptPackBuilder: 5 Disclosure Phases & Redaction Proof

- **File:** `k1/fabric/prompt_pack/builder.py`
- **Design:** Builds the LLM-facing prompt pack from a `ResolutionEnvelope`. This is the bridge between the resolver's structured output and Back's LLM context window. 5 disclosure phases gate what fields are visible at each stage. Redaction leak detection ensures no secret markers reach the LLM.

**Key design decisions (derived from Epics 1–5):**

1. **5 disclosure phases with field whitelisting.** Each phase has a fixed set of allowed fields. Fields not in the allowed set are replaced with empty defaults. This prevents the LLM from seeing schema details before tool selection, or forbidden tools before prerequisites complete.

2. **Constitution cards from typed ConstitutionArtifact, not raw dicts.** `PromptPackBuilder` takes a `ConstitutionLoader` and calls `loader.get_prerequisite_reads()`, `loader.get_hil_gates()`, etc. The `ConstitutionCard` dataclass has typed fields (`preconditions: list[str]`, `companion_resource_roles: dict[str, Any]`, `verification_requirement: str`) — not raw dict access.

3. **Guide cards from ConnectorDefinition, not YAML files.** After Epic 9–13 migrate activity profiles into `ToolDefinition.guide_cards`, `PromptPackBuilder` reads guide cards from `GlobalProjectionStore` (ingested via `ManifestAdmissionService`). No YAML file scanning.

4. **Redaction leak detection on BOTH source and rendered output.** Before building: `redaction_check(envelope.to_dict())` — reject if source contains secret markers. After building: `redaction_check(pack.to_dict())` — reject if rendered pack leaks secrets. After rendering: `redaction_check(rendered_string)` — reject if rendered text leaks secrets. Triple-check.

5. **Stale cards flagged, not hidden.** If a candidate's `freshness_state == 'stale'`, the card is included but flagged `stale=True`. The LLM sees the stale marker and can request a refresh. This is better than hiding stale data (which would mislead the LLM).

**Dataclasses:**

  ```python
  @dataclass(frozen=True)
  class ConstitutionCard:
      """One connector's constitution, rendered for LLM consumption."""
      connector_id: str
      label: str                           # human-readable connector name
      preconditions: list[str]             # from ConstitutionArtifact.prerequisite_reads
      companion_resource_roles: dict[str, Any]  # from ConstitutionArtifact.companion_resource_roles
      verification_requirement: str        # from ConstitutionArtifact.verification_requirements
      stale: bool = False                  # True if any resource behind this card is stale

  @dataclass(frozen=True)
  class ToolNameCard:
      """One available tool, rendered for LLM tool selection."""
      capability_name: str                 # "tool.execute.family.calendar.create"
      description: str                     # from CapabilityRecord.description
      role: str                            # 'primary' | 'companion' | 'prerequisite' | 'verifier'
      stale: bool = False

  @dataclass(frozen=True)
  class PolicyCard:
      """Policy constraints for one connector."""
      connector_id: str
      what_is_required: str                # human-readable: "parent role required for write"
      what_triggers_hil: list[str]         # conditions that force human-in-the-loop
      what_is_denied: list[str]            # denied actions + reasons
      stale: bool = False

  @dataclass(frozen=True)
  class GuideCard:
      """LLM-facing execution guidance."""
      guide_id: str
      title: str
      content: str                         # markdown — the actual LLM instructions
      relevance: str                       # 'always' | 'on_conflict' | 'on_error'
      stale: bool = False

  @dataclass(frozen=True)
  class SchemaCard:
      """Full JSON Schema for a committed capability."""
      capability_name: str
      binding_id: str
      input_schema: dict[str, Any]         # JSON Schema Draft-07
      required_fields: list[str]
      optional_fields: list[str]
      stale: bool = False

  @dataclass(frozen=True)
  class RedactionEvidence:
      """Proof that no secret markers leaked into the prompt."""
      redaction_id: str
      prompt_hash: str                     # SHA-256 of the final rendered prompt
      fields_redacted: list[str]           # fields that were removed
      fields_verified_absent: list[str]    # fields confirmed absent
      prompt_visible_leak_count: int       # must be 0
      verdict: str                         # 'pass' | 'fail'

  @dataclass(frozen=True)
  class PromptPack:
      """Complete LLM-facing prompt pack with staged disclosure."""
      prompt_pack_id: str
      react_state: str                     # 'needs_prerequisite' | 'ready_to_execute' | 'needs_hil' | 'blocked'
      target_tier: str
      disclosure_phase: str                # 'connector_summary' | 'tool_name_selection' | 'schema_binding' | 'execution' | 'post_execution'
      source_refs: list[str]               # [resolution_id, request_id]
      source_versions: dict[str, str]      # version tracking
      candidate_summary: dict[str, Any]    # what resources/persons were found
      connector_constitution_cards: list[ConstitutionCard]
      tool_name_cards: list[ToolNameCard]
      policy_cards: list[PolicyCard]
      guide_cards: list[GuideCard]
      selected_schema_cards: list[SchemaCard]
      decision_surface: str                # "verdict=can_execute; next_actions=3"
      uncertainty_markers: list[str]       # "ambiguous_person", "stale_resource"
      omission_summary: str                # why some connectors were excluded
      allowed_tool_calls: list[str]        # capability_names Back may invoke
      forbidden_tool_calls: list[str]      # capability_names Back must NOT invoke yet
      allowed_next_actions: list[str]      # human-readable next steps
      hil_options: list[dict[str, Any]]    # HIL prompts when verdict == 'needs_hil' or 'needs_disambiguation'
      redaction_summary: RedactionEvidence
      expires_at: str                      # 5-min TTL
  ```

**Phase whitelist** (fields visible at each disclosure phase):

  ```python
  PHASE_ALLOWED_FIELDS: dict[str, set[str]] = {
      "loop_start": {"candidate_summary", "uncertainty_markers"},
      "connector_summary": {
          "connector_constitution_cards", "tool_name_cards", "policy_cards",
          "guide_cards", "candidate_summary", "omission_summary",
          "allowed_next_actions", "forbidden_next_actions",
      },
      "tool_name_selection": {
          "tool_name_cards", "allowed_next_actions",
          "decision_surface", "hil_options",
      },
      "schema_binding": {"selected_schema_cards", "allowed_tool_calls"},
      "execution": {"allowed_tool_calls", "allowed_next_actions"},
      "post_execution": {"candidate_summary", "verification_result"},
  }
  ```

**API:**

  ```python
  class PromptPackBuilder:
      def __init__(self,
                   global_store: GlobalProjectionStore,
                   *,
                   constitution_loader: ConstitutionLoader | None = None,
                   ): ...

      def build(self,
                resolution_envelope: ResolutionEnvelope,
                *,
                disclosure_phase: str,
                prompt_budget_tokens: int = 8000,
                committed_tool_names: list[str] | None = None,
                ) -> PromptPack:
          """Build a staged-disclosure PromptPack from a ResolutionEnvelope.

          1. Redaction check on source envelope → reject if secrets present.
          2. Build cards from typed sources:
             - ConstitutionCards: from ConstitutionLoader (Epic 5.2), not raw store.
             - ToolNameCards: from BindingBundle.tool_name_cards.
             - PolicyCards: from PolicyBundle.
             - GuideCards: from GlobalProjectionStore (ingested from ConnectorDefinition.guide_cards).
             - SchemaCards: from CapabilityRecord (only for committed_tool_names in schema_binding phase).
          3. Apply phase whitelist → zero out non-allowed fields.
          4. Redaction check on final pack → reject if secrets leaked.
          5. Compute SHA-256 hash of the serialized pack.
          6. Return PromptPack with RedactionEvidence.
          """

      def render(self, pack: PromptPack, *, budget_tokens: int | None = None) -> str:
          """Render a PromptPack to a markdown string for LLM consumption.
          Budget-aware: truncates to budget_tokens if provided.
          Final redaction check on rendered output."""

      # ── Internal card builders ──
      def _constitution_cards(self, envelope: ResolutionEnvelope) -> list[ConstitutionCard]: ...
      def _policy_cards(self, envelope: ResolutionEnvelope) -> list[PolicyCard]: ...
      def _guide_cards(self, envelope: ResolutionEnvelope) -> list[GuideCard]: ...
      def _schema_cards(self, envelope: ResolutionEnvelope,
                        committed_tool_names: list[str]) -> list[SchemaCard]: ...
      def _apply_phase(self, pack: PromptPack, phase: str) -> PromptPack: ...
  ```

- **Coherence check with Epic 5.1:** `ConstitutionCard.preconditions` is built from `ConstitutionArtifact.prerequisite_reads` (a `list[PrerequisiteRead]`), not from raw dict access. Each `PrerequisiteRead` has typed fields: `operation`, `resource_kind`, `reason`, `required`, `timeout_ms`.
- **Coherence check with Epic 2.3:** `GuideCard.content` is the full markdown from `ConnectorDefinition.guide_cards[n].content`. This was formerly in YAML `template_file` references — now it's inline in the `ToolDefinition`.
- **Coherence check with Epic 9–13:** After family tools are upgraded, guide cards are populated from `ToolDefinition.guide_cards` → ingested into `GlobalProjectionStore` → read by `PromptPackBuilder._guide_cards()`.
- **Redaction proof (proven by POC):** `SECRET_MARKERS` list is checked via `redaction_check()`. Any field whose value contains a secret marker (like `"RESTRICTED:"` prefix) is flagged as a leak. This prevents internal state from reaching the LLM.
- **Verify:** `python -c "from k1.fabric.prompt_pack.builder import PromptPackBuilder, PromptPack, ConstitutionCard, ToolNameCard, PolicyCard, GuideCard, SchemaCard, RedactionEvidence"`

---

### Issue 6.4 — Tests

- **GAP-P1-020:** `tests/k1/fabric/resolver/test_capability_binder.py`
  - `TestTypedIntentBinding` — Pass 1: graph-resolved intent → exact capability match via capability_type_index
  - `TestExactMatchBinding` — Pass 2: resource_kind + invocation_mode + effect → exact match
  - `TestBM25FallbackBinding` — Pass 3: action text → FTS5 BM25 search → ranked results
  - `TestPassPrecedence` — Pass 1 result preferred over Pass 2, Pass 2 over Pass 3
  - `TestRolePropagation` — ResolvedIntentType.role → CapabilityBinding.role
  - `TestCompanionDiscovery` — constitution.companion_resource_roles → companion bindings
  - `TestPrerequisiteDiscovery` — constitution.prerequisite_reads → prerequisite bindings
  - `TestPolicyBlock` — denied candidate → UnboundRole(reason='policy_block')
  - `TestStaleResourceBlock` — stale candidate + write intent → UnboundRole(reason='stale_projection')
  - `TestMissingCapability` — no match after all 3 passes → UnboundRole(reason='missing_capability')
  - `TestBindingDedup` — duplicate (connector_id, cap_name, resource_id, actor_id, session_id) → single binding
  - `TestToolSelectionCommit` — valid commit, rejected tools, partial acceptance
  - `TestBindingBundleRoles` — primary/companions/prerequisites/verifiers/alternatives correctly separated
  - `TestInvocationModeEffectMapping` — "list"→("read","read"), "create"→("execute","write"), etc.

- **GAP-P1-001:** `tests/k1/fabric/resolver/test_situated_resolver.py` — all 13 verdicts with sub-reason
  - `TestHappyPath` — can_execute for valid calendar create with all prerequisites completed
  - `TestCanExecuteWithGate` — prerequisite read not completed → sub_reason includes which prerequisite
  - `TestMissingCapability` — unknown resource kind → sub_reason includes resource_kind
  - `TestBlockedByPolicy` — role not allowed → sub_reason includes deny_reason
  - `TestStaleProjection` — write on stale resource → sub_reason includes resource_id
  - `TestNeedsDisambiguation` — ambiguous person ref → sub_reason includes raw name
  - `TestMissingRequiredParams` — no subject/params/time → sub_reason='intent_too_vague'
  - `TestPromoteToTier3` — 6+ connectors → sub_reason includes connector count
  - `TestCannotExecute` — budget exhausted, duplicate idempotency
  - `TestHILGateTriggered` — missing_required_field HIL gate → sub_reason includes trigger name
  - `TestConflictRuleTriggered` — time_overlap conflict → sub_reason includes conflict details
  - `TestConstitutionLoaded` — constitution loaded from ConstitutionLoader (not raw store)
  - `TestIdempotencyEnforced` — duplicate idempotency key → cannot_execute
  - `TestFullPipeline` — end-to-end: frame → universe → types → policy → binder → constitution → verdict

- **GAP-P1-009:** `tests/k1/fabric/resolver/test_situated_resolver_negative.py`
  - Missing capability → correct error with resource_kind
  - Blocked by policy → correct error with deny_reason
  - Incomplete world projection → cannot_execute with completeness='partial'
  - Stale projection → stale_projection with refresh directive
  - Budget exhausted → cannot_execute with budget field name
  - Intent too vague → missing_required_params

- **GAP-P1-011:** `tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py`
  - `TestPromptPackShape` — valid PromptPack structure, all fields present
  - `TestStagedDisclosure` — correct cards per phase (8 tests, one per phase+field combo)
  - `TestRedactionProof` — secret markers removed from source, pack, rendered (8 tests)
  - `TestConstitutionCards` — rendered from ConstitutionArtifact typed fields (5 tests)
  - `TestToolNameCards` — capability names with roles (4 tests)
  - `TestPolicyCards` — what is required/denied/triggers HIL (4 tests)
  - `TestGuideCards` — guide cards from store, not YAML (4 tests)
  - `TestSchemaCards` — JSON Schema rendered correctly, only for committed tools (5 tests)
  - `TestStaleCardPolicy` — stale cards flagged but not hidden (5 tests)
  - `TestForbiddenActionGating` — forbidden tools excluded from allowed_tool_calls (4 tests)
  - `TestRenderBudget` — rendered output respects token budget truncation (3 tests)
  - `TestPhaseFieldWhitelist` — each phase only exposes allowed fields (6 tests)

- **Run:** `pytest tests/k1/fabric/resolver/test_capability_binder.py tests/k1/fabric/resolver/test_situated_resolver.py tests/k1/fabric/resolver/test_situated_resolver_negative.py tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py -v`

---

### System Coherence: Epic 6 in Context

```
                    ┌──────────────────────────────────────────┐
                    │        ResolveSituationService            │
                    │  (Issue 6.2 — 13-step verdict cascade)    │
                    └────┬──────┬──────┬──────┬──────┬─────────┘
                         │      │      │      │      │
              ┌──────────┘      │      │      │      └──────────┐
              ▼                 ▼      ▼      ▼                 ▼
    ┌──────────────────┐  ┌──────────┐ ┌────────────┐ ┌──────────────────┐
    │ ResolveResources │  │Capability│ │PolicySelector│ │ConstitutionLoader│
    │    Service       │  │  Type    │ │  (Epic 4.1) │ │   (Epic 5.2)    │
    │   (Epic 3.4)     │  │ Resolver │ │             │ │                  │
    │                  │  │(Epic 3.5)│ │             │ │                  │
    └────────┬─────────┘  └────┬─────┘ └──────┬──────┘ └────────┬─────────┘
             │                 │              │                  │
             ▼                 ▼              ▼                  ▼
    ┌──────────────────┐  ┌──────────────────────────────────────────────┐
    │  LocalProjection │  │          GlobalProjectionStore                │
    │      Store       │  │  capabilities, connectors, graph ontology,    │
    │   (Epic 1.5)     │  │  constitutions, resource_kinds, FTS5         │
    └──────────────────┘  │               (Epic 1.1–1.4)                 │
                          └────────────────────┬─────────────────────────┘
                                               │
                          ┌────────────────────┘
                          ▼
                 ┌──────────────────┐
                 │CapabilityBinder  │  ◄── Issue 6.1
                 │   Service        │  3-pass: typed → exact → BM25
                 │                  │  Output: BindingBundle
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ PromptPackBuilder│  ◄── Issue 6.3
                 │                  │  5 disclosure phases, redaction-proof
                 │                  │  Output: PromptPack → Back's LLM
                 └──────────────────┘
```

**Data flow for a successful resolution:**

1. `RequestFrame` → `ResolveResourcesService.resolve()` → `ResourceUniverse`
2. `RequestFrame` + `ResourceUniverse` → `CapabilityTypeResolver.resolve()` → `list[ResolvedIntentType]`
3. `ResourceUniverse` + `list[ResolvedIntentType]` → `PolicySelectorService.select()` → `PolicyBundle`
4. `ResolvedIntentType[]` + `ResourceUniverse` + `PolicyBundle` → `CapabilityBinderService.bind()` → `BindingBundle`
5. `BindingBundle.primary.connector_id` → `ConstitutionLoader.load()` → `ConstitutionArtifact`
6. `ResolutionEnvelope` + `ConstitutionArtifact` → `PromptPackBuilder.build()` → `PromptPack`
7. `ResolutionEnvelope` (with verdict + prompt_pack) → Back receives complete resolution snapshot

**Back's consumption path:**

- `ResolutionEnvelope.verdict` → Back's `_determine_action()` decides: execute, ask HIL, refresh, promote, or abort
- `ResolutionEnvelope.prompt_pack` → injected into Back's LLM context at the appropriate disclosure phase
- `ResolutionEnvelope.allowed_capability_names` → Back's `_select_tool()` chooses from authorized capabilities
- `ResolutionEnvelope.capability_name_to_binding` → Back's `_invoke_capability()` maps chosen tool to binding ID

---

## Epic 7: Wiring — Fabric Dataclass, Factory, Kernel Service

**Goal:** Wire all promoted components from Epics 1–6 into the existing Fabric infrastructure. Three integration points: (1) `Fabric` dataclass gets new fields + a `resolve_situation` meta-tool, (2) `FabricFactory._construct_fabric()` gets step 21 wiring, (3) `KernelService._startup_tier1()` gets store lifecycle + domain catalog loading + per-session wiring.

**Design derivation from Epics 1–6:**

Every component's constructor signature is defined in its Epic. This Epic does NOT redesign constructors — it wires them. The dependency graph below is derived exclusively from `__init__` signatures in Epics 1–6.

```
                    ┌──────────────────────────────────────┐
                    │         GlobalProjectionStore         │  Epic 1.1–1.4
                    │  (shared: created ONCE at S2.10)     │
                    └──┬──────┬──────┬──────┬──────┬───────┘
                       │      │      │      │      │
          ┌────────────┘      │      │      │      └──────────────┐
          ▼                   ▼      ▼      ▼                     ▼
┌─────────────────┐  ┌────────────┐ ┌──────────────┐  ┌────────────────────┐
│ ConstitutionLoader│  │PolicySelector│ │CapabilityType│  │  PromptPackBuilder │
│   (Epic 5.2)     │  │  (Epic 4.1) │ │  Resolver    │  │    (Epic 6.3)      │
│                  │  │             │ │  (Epic 3.5)  │  │                    │
│ created ONCE     │  │ per-session │ │ per-session  │  │ per-session        │
└───┬──────────────┘  └─────────────┘ └──────┬───────┘  └────────────────────┘
    │                                        │
    │          ┌─────────────────────────────┘
    │          ▼
    │  ┌──────────────────────┐     ┌──────────────────────┐
    │  │ ResolveResourcesService│     │ CapabilityBinderService│
    │  │     (Epic 3.4)        │     │     (Epic 6.1)         │
    │  │ per-session            │     │ per-session            │
    │  └───────────┬────────────┘     └───────────┬────────────┘
    │              │                              │
    │              └──────────┬───────────────────┘
    │                         ▼
    │              ┌──────────────────────────────┐
    │              │   ResolveSituationService     │  Epic 6.2
    │              │   per-session                 │
    │              │   depends on ALL of the above │
    │              └──────────────────────────────┘
    │
    ▼
┌──────────────────────┐
│ VerificationPlanRunner│  Epic 4.2
│ created ONCE by kernel│
│ after providers ready │
│ needs NativeProvider  │
└──────────────────────┘

┌──────────────────────┐     ┌──────────────────────┐
│  LocalProjectionStore │     │   IdempotencyStore    │
│  per-session          │     │   shared              │
│  :memory: by default  │     │   created ONCE        │
└──────────────────────┘     └──────────────────────┘
```

**Shared vs per-session split:**

| Component | Shared (once) | Per-Session | Rationale |
|-----------|--------------|-------------|-----------|
| `GlobalProjectionStore` | ✓ | — | Single source of truth for all capabilities, connectors, graph ontology |
| `IdempotencyStore` | ✓ | — | Must prevent duplicates across ALL sessions |
| `ConstitutionLoader` | ✓ | — | Reads shared store, no session state |
| `LocalProjectionStore` | — | ✓ | Per-household connected resources, members, aliases |
| `ResolveResourcesService` | — | ✓ | Reads local store (per-household) |
| `CapabilityTypeResolver` | — | ✓ | Reads local store for alias resolution |
| `PolicySelectorService` | — | ✓ | Gates per actor + per resource context (though it could be shared — reads only global store — keeping per-session for consistency) |
| `CapabilityBinderService` | — | ✓ | Reads local store for freshness |
| `ResolveSituationService` | — | ✓ | Orchestrates per-request resolution |
| `PromptPackBuilder` | — | ✓ | Builds per-request LLM context |
| `VerificationPlanRunner` | ✓ | — | Post-write verification gates all sessions; needs NativeProviderDispatch |

**Why VerificationPlanRunner is shared (not per-session):** The verifier runs AFTER capability execution (which is already per-session). It needs `NativeProviderDispatch` to perform readback verification. There is ONE native provider registry per kernel — it doesn't vary by session. Creating multiple verifier instances would mean multiple references to the same provider dispatch, adding unnecessary complexity.

---

### Issue 7.1 — fabric.py: Fabric Dataclass Fields + Meta-Tool

- **File:** `k1/fabric/fabric.py`
- **Design:** Add 8 new fields to the `Fabric` dataclass. Add a `resolve_situation` meta-tool with a typed handler. Zero impact on existing code paths — all fields default to `None`, meta-tool is additive.

**New Fabric fields:**

  ```python
  @dataclass
  class Fabric:
      # ... existing fields unchanged (facade, retrieval, registry_api, etc.) ...

      # ── Phase 1 promoted components (all default None — backward compatible) ──
      global_projection_store: GlobalProjectionStore | None = None   # Epic 1 — shared across sessions
      local_projection_store: LocalProjectionStore | None = None     # Epic 1 — per-session
      idempotency_store: IdempotencyStore | None = None              # Epic 1 — shared
      situated_resolver: ResolveSituationService | None = None       # Epic 6.2 — per-session
      policy_selector: PolicySelectorService | None = None           # Epic 4.1 — per-session
      verification_runner: VerificationPlanRunner | None = None      # Epic 4.2 — shared (wired by kernel)
      constitution_loader: ConstitutionLoader | None = None          # Epic 5.2 — shared
      prompt_pack_builder: PromptPackBuilder | None = None           # Epic 6.3 — per-session
  ```

**Imports (add to top of fabric.py):**

  ```python
  # Phase 1 imports — lazy, only when meta-tool is invoked
  from __future__ import annotations
  # ... existing imports unchanged ...
  ```

**Meta-tool registration** (in the method that registers `discover_capabilities`, `invoke_capability`, `build_agent`):

  ```python
  # Register resolve_situation alongside existing meta-tools
  self._register_meta_tool(
      "resolve_situation",
      handler=self._handle_resolve_situation,
      description="Resolve a user intent into a situated execution plan with capability bindings, policy gates, and constitution enforcement.",
      input_schema={
          "type": "object",
          "required": ["request_id", "frame", "actor_id", "space_id", "session_id"],
          "properties": {
              "request_id": {"type": "string"},
              "frame": {"type": "object"},            # RequestFrame serialized
              "actor_id": {"type": "string"},
              "space_id": {"type": "string"},
              "session_id": {"type": "string"},
              "tier": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
              "safety_band": {"type": "string", "enum": ["GREEN", "AMBER", "RED"]},
              "disclosure_phase": {"type": "string"},
              "prompt_budget_tokens": {"type": "integer"},
              "completed_prerequisite_bindings": {"type": "array", "items": {"type": "string"}},
              "idempotency_keys": {"type": "array", "items": {"type": "string"}},
              "budget_remaining": {"type": "object"},
          },
      },
  )
  ```

**Meta-tool handler:**

  ```python
  async def _handle_resolve_situation(self, payload: dict[str, Any]) -> dict[str, Any]:
      """Meta-tool handler for resolve_situation.

      Deserializes the incoming payload into a ResolveSituationRequest,
      delegates to self.situated_resolver.resolve(), and returns the
      ResolutionEnvelope as a dict.

      Error handling:
          - situated_resolver is None → returns error envelope with
            verdict='cannot_execute', sub_reason='resolver_not_wired'.
          - ValidationError on request parsing → returns error envelope.
          - Unexpected exception → returns error envelope with diagnostics.
      """
      if self.situated_resolver is None:
          return {
              "resolution_id": f"err_{uuid.uuid4().hex[:12]}",
              "verdict": "cannot_execute",
              "sub_reason": "resolver_not_wired",
              "diagnostics": [{"type": "wiring", "message": "situated_resolver is None — Phase 1 stores not wired"}],
          }

      try:
          from k1.fabric.resolver.situated_resolver import ResolveSituationRequest
          from k1.fabric.resolver.request_frame import RequestFrame

          # Deserialize the frame from the payload dict
          frame_dict = payload.get("frame", {})
          frame = RequestFrame(
              request_id=payload["request_id"],
              task_id=payload.get("task_id", ""),
              trace_id=payload.get("trace_id", ""),
              actor_id=payload["actor_id"],
              space_id=payload["space_id"],
              intents=[],  # populated by RequestFrameBuilder if frame_dict has intents
              created_at=datetime.now(timezone.utc).isoformat(),
          )
          # If frame_dict has intents, use RequestFrameBuilder
          if frame_dict.get("intents"):
              from k1.fabric.resolver.request_frame_builder import RequestFrameBuilder
              builder = RequestFrameBuilder()
              envelope = _make_minimal_envelope(payload, frame_dict)
              frame = builder.build(envelope)

          request = ResolveSituationRequest(
              request_id=payload["request_id"],
              frame=frame,
              actor_id=payload["actor_id"],
              space_id=payload["space_id"],
              session_id=payload["session_id"],
              tier=payload.get("tier", "MEDIUM"),
              safety_band=payload.get("safety_band", "GREEN"),
              disclosure_phase=payload.get("disclosure_phase", "connector_summary"),
              prompt_budget_tokens=payload.get("prompt_budget_tokens", 8000),
              completed_prerequisite_bindings=payload.get("completed_prerequisite_bindings", []),
              idempotency_keys=payload.get("idempotency_keys", []),
              budget_remaining=payload.get("budget_remaining"),
          )
          envelope = self.situated_resolver.resolve(request)
          return envelope.to_dict()

      except Exception as exc:
          logger.error("_handle_resolve_situation failed: %s", exc, exc_info=True)
          return {
              "resolution_id": f"err_{uuid.uuid4().hex[:12]}",
              "verdict": "cannot_execute",
              "sub_reason": "handler_exception",
              "diagnostics": [{"type": "handler_error", "error": str(exc)}],
          }
  ```

- **Risk:** Zero. New fields default to `None` — nothing reads them until the kernel wires them. New meta-tool is purely additive. No existing meta-tool behavior changes.
- **Existing tests must pass:** All 113 fabric tests unchanged.
- **Verify:** `python -c "from k1.fabric.fabric import Fabric; f = Fabric.__dataclass_fields__; assert 'situated_resolver' in f; assert f['situated_resolver'].default is None"`

---

### Issue 7.2 — factory.py: FabricFactory Step 21 Wiring

- **File:** `k1/fabric/factory.py`
- **Design:** Add `global_projection_store`, `local_projection_store`, `idempotency_store` parameters to `create_shared()` and `create_with_ports()`. Thread them through to `_construct_fabric()`. Add step 21 after the existing 20 steps.

**New parameters on `create_shared()`:**

  ```python
  @staticmethod
  def create_shared(
      event_port: Any, bridge: Any, model_gateway: Any,
      prompt_system: Any, delta_bus: Any,
      *,
      # ... all existing params unchanged ...
      global_projection_store: GlobalProjectionStore | None = None,    # NEW
      idempotency_store: IdempotencyStore | None = None,               # NEW
  ) -> Fabric:
  ```

**New parameters on `create_with_ports()`:**

  ```python
  @staticmethod
  def create_with_ports(
      state_reader: ISessionStateReader, event_port: IEventPort,
      bridge: IFabricK0Port, model_gateway: IModelGatewayPort,
      prompt_system: IPromptSystemPort, delta_bus: IDeltaBusPort,
      *,
      # ... all existing params unchanged ...
      global_projection_store: GlobalProjectionStore | None = None,    # NEW
      local_projection_store: LocalProjectionStore | None = None,      # NEW (per-session only)
      idempotency_store: IdempotencyStore | None = None,               # NEW
  ) -> Fabric:
  ```

**New parameter on `_construct_fabric()`:**

  ```python
  def _construct_fabric(
      # ... all 16 existing params unchanged ...
      global_projection_store: GlobalProjectionStore | None = None,    # NEW
      local_projection_store: LocalProjectionStore | None = None,      # NEW
      idempotency_store: IdempotencyStore | None = None,               # NEW
  ) -> Fabric:
  ```

**Step 21 — Wire Phase 1 components** (after existing step 20 "Assemble + return Fabric"):

  ```python
  # ===== STEP 21 (NEW): Wire Phase 1 promoted components =====
  # Gated: only wires when global_projection_store is provided.
  # When None (tests, standalone, legacy paths), nothing changes.
  if global_projection_store is not None:

      # ── 21a: Attach stores to Fabric ──
      fabric.global_projection_store = global_projection_store
      fabric.idempotency_store = idempotency_store

      # ── 21b: Create shared components (no per-session state) ──
      from k1.fabric.constitution.loader import ConstitutionLoader

      constitution_loader = ConstitutionLoader(global_projection_store)
      fabric.constitution_loader = constitution_loader

      # ── 21c: Create or receive local store ──
      # NEVER fall back to global store as local — create separate
      # in-memory instance when none provided.
      from k1.fabric.stores.local_projection_store import LocalProjectionStore

      local_store = local_projection_store or LocalProjectionStore(":memory:")
      fabric.local_projection_store = local_store

      # ── 21d: Wire resolver sub-components ──
      from k1.fabric.resolver.resource_projection import ResolveResourcesService
      from k1.fabric.resolver.capability_type_resolver import CapabilityTypeResolver
      from k1.fabric.resolver.capability_binder import CapabilityBinderService
      from k1.fabric.policy.selector import PolicySelectorService
      from k1.fabric.prompt_pack.builder import PromptPackBuilder

      resource_resolver = ResolveResourcesService(global_projection_store, local_store)
      type_resolver = CapabilityTypeResolver(global_projection_store, local_store)
      policy_selector = PolicySelectorService(global_projection_store)
      capability_binder = CapabilityBinderService(global_projection_store, local_store)
      prompt_pack_builder = PromptPackBuilder(
          global_projection_store,
          constitution_loader=constitution_loader,
      )

      fabric.policy_selector = policy_selector
      fabric.prompt_pack_builder = prompt_pack_builder

      # ── 21e: Wire situated resolver (depends on all of the above) ──
      from k1.fabric.resolver.situated_resolver import ResolveSituationService

      fabric.situated_resolver = ResolveSituationService(
          global_store=global_projection_store,
          local_store=local_store,
          resource_resolver=resource_resolver,
          type_resolver=type_resolver,
          policy_selector=policy_selector,
          capability_binder=capability_binder,
          constitution_loader=constitution_loader,
          prompt_pack_builder=prompt_pack_builder,
          idempotency_store=idempotency_store,
      )

      # ── 21f: Wire idempotency into CapabilityFabric._execute_impl ──
      # Step 0 of the 9-step execution pipeline checks idempotency
      # before any provider dispatch. The store is attached directly
      # to the facade so _execute_impl can call self._idempotency_store.check().
      if idempotency_store is not None:
          fabric.facade._idempotency_store = idempotency_store

      # ── 21g: VerificationPlanRunner — NOT wired here ──
      # VerificationPlanRunner needs NativeProviderDispatch, which only
      # exists after the kernel registers providers (S8 family tools).
      # The kernel wires fabric.verification_runner in service.py after S8.
      # See Issue 7.3 for the wiring point.

      logger.info(
          "Phase 1 wiring complete: global_store=%s local_store=%s idempotency=%s "
          "constitution_loader=%s situated_resolver=%s prompt_pack_builder=%s",
          type(global_projection_store).__name__,
          type(local_store).__name__,
          type(idempotency_store).__name__ if idempotency_store else "None",
          type(constitution_loader).__name__,
          type(fabric.situated_resolver).__name__,
          type(prompt_pack_builder).__name__,
      )
  ```

- **Coherence check — ResolveSituationService constructor** (Epic 6.2): Receives ALL 8 optional dependencies. The factory provides all 8. If any are `None`, the service creates defaults internally (as defined in Epic 6.2's `__init__`).
- **Coherence check — PromptPackBuilder constructor** (Epic 6.3): Receives `constitution_loader` so it can build `ConstitutionCard` from typed `ConstitutionArtifact`, not raw store dicts.
- **Coherence check — NEVER global-as-local** (Fix from Epic 1 review): `local_store` is either the provided `local_projection_store` or `LocalProjectionStore(":memory:")`. Never `global_projection_store`.
- **Risk:** Zero — all gated behind `if global_projection_store is not None`. Standalone/testing paths (which pass `None`) have zero behavior change.
- **Existing tests must pass:** All 113 fabric tests unchanged.
- **Verify:** `python -c "from k1.fabric.factory import FabricFactory; import inspect; sig = inspect.signature(FabricFactory.create_shared); assert 'global_projection_store' in sig.parameters"`

---

### Issue 7.3 — service.py: Kernel Lifecycle Integration

- **File:** `k1/kernel/service.py`
- **Design:** Five integration points in the kernel lifecycle:
  1. **S2.10** (new): Create + open `GlobalProjectionStore` and `IdempotencyStore` BEFORE S3 Fabric creation.
  2. **S3**: Pass stores to `FabricFactory.create_shared()`.
  3. **Post-S8**: Load domain catalog into `GlobalProjectionStore` via `ManifestAdmissionService`. Wire `VerificationPlanRunner`.
  4. **P3** (per-session): Pass shared stores + create per-session `LocalProjectionStore`.
  5. **Shutdown**: Close stores after `shared_fabric.shutdown()`.

**KernelService new fields:**

  ```python
  class KernelService:
      def __init__(self, config: KernelConfig) -> None:
          # ... existing fields unchanged ...

          # Phase 1: shared stores (populated at S2.10)
          self._global_projection_store: GlobalProjectionStore | None = None
          self._idempotency_store: IdempotencyStore | None = None
  ```

**Integration point 1 — S2.10 (new step, before S3):**

  ```python
  # ── S2.10: Phase 1 stores (before S3 Fabric) ───────────
  # Created BEFORE shared Fabric so the factory can wire them
  # into the Fabric instance. These are standalone SQLite files —
  # no dependencies on bus, bridge, or model hub.
  from k1.fabric.stores.global_projection_store import GlobalProjectionStore
  from k1.fabric.stores.idempotency_store import IdempotencyStore

  global_store = GlobalProjectionStore(
      db_path=self._config.global_projection_db_path or "./data/global_projection.db"
  )
  global_store.open()
  self._global_projection_store = global_store

  idempotency_store = IdempotencyStore(
      db_path=self._config.idempotency_db_path or "./data/idempotency.db"
  )
  idempotency_store.open()
  self._idempotency_store = idempotency_store

  self._log_lifecycle("S2.10_complete", "GlobalProjectionStore+IdempotencyStore")
  ```

**Integration point 2 — S3 (pass stores to shared Fabric):**

  ```python
  # Inside S3, add to the existing FabricFactory.create_shared() call:
  self._shared_fabric = FabricFactory.create_shared(
      event_port=event_port,
      bridge=bridge_adapter,
      model_gateway=model_gateway,
      prompt_system=prompt_system,
      delta_bus=delta_bus,
      state_reader=session_routing_reader,
      hil_port=self._hil_service,
      # ── Phase 1 stores ──
      global_projection_store=self._global_projection_store,
      idempotency_store=self._idempotency_store,
  )
  ```

**Integration point 3 — Post-S8 (load domain catalog + wire verifier):**

  ```python
  # ── Phase 1: Load domain catalog into GlobalProjectionStore ──
  # Runs after S8 family-tools bootstrap, when NativeToolProvider is
  # registered and ready. Loads the domain catalog (50 connector
  # definitions) into the store so resolve_situation can discover them.
  if self._shared_fabric is not None:
      gps = getattr(self._shared_fabric, 'global_projection_store', None)
      if gps is not None:
          from k1.fabric.connectors.domain_catalog import DOMAIN_SERVICES, build_domain_corpus
          from k1.fabric.manifest_admission import ManifestAdmissionService

          admission = ManifestAdmissionService(gps)
          for domain_id in DOMAIN_SERVICES:  # family, enterprise, government, agriculture, healthcare
              manifests = build_domain_corpus(domain_id)
              results = admission.admit_all(manifests)
              admitted = sum(1 for r in results if r.admission_verdict == 'admitted')
              logger.info(
                  "Phase 1 catalog loaded: domain=%s connectors=%d admitted=%d",
                  domain_id, len(manifests), admitted,
              )

          # ── Wire VerificationPlanRunner (needs NativeProviderDispatch) ──
          # The native provider is registered during S8 bootstrap.
          # We retrieve it from the shared Fabric's provider factory.
          from k1.fabric.verification.runner import VerificationPlanRunner

          native_provider = _get_native_provider(self._shared_fabric)
          if native_provider is not None:
              constitution_loader = getattr(
                  self._shared_fabric, 'constitution_loader', None
              )
              self._shared_fabric.verification_runner = VerificationPlanRunner(
                  native_provider=native_provider,
                  global_store=gps,
                  constitution_loader=constitution_loader,
              )
              logger.info("Phase 1: VerificationPlanRunner wired")
  ```

**Integration point 4 — P3 (per-session wiring):**

  ```python
  # Inside _create_session_tier2(), in the per-session Fabric creation step.
  # The per-session Fabric receives:
  #   - Shared GlobalProjectionStore reference (read-only — writes go through
  #     ManifestAdmissionService at bootstrap time)
  #   - Shared IdempotencyStore reference (all sessions share one)
  #   - NEW per-session LocalProjectionStore (in-memory, isolated)
  from k1.fabric.stores.local_projection_store import LocalProjectionStore

  session_local_store = LocalProjectionStore(":memory:")
  session_local_store.open()

  session.fabric = FabricFactory.create_with_ports(
      state_reader=session_state_reader,
      event_port=per_session_event_port,
      bridge=bridge_adapter,
      model_gateway=model_gateway,
      prompt_system=self._prompt_system,
      delta_bus=delta_bus,
      production_mode=False,
      capability_registry=self._shared_fabric.registry,
      hil_port=session_hil_port if self._hil_service else None,
      # ── Phase 1: shared stores + per-session local store ──
      global_projection_store=self._global_projection_store,
      local_projection_store=session_local_store,
      idempotency_store=self._idempotency_store,
  )
  # Attach local store to session for teardown
  session.local_projection_store = session_local_store
  ```

**Integration point 5 — Shutdown (close stores):**

  ```python
  # In shutdown(), AFTER shared_fabric.shutdown() and AFTER
  # family_tools.close(), add:
  if self._global_projection_store is not None:
      try:
          self._global_projection_store.close()
          self._log_lifecycle("Phase1_store_closed", "GlobalProjectionStore")
      except Exception as exc:
          errors.append(exc)
          logger.warning("shutdown: GlobalProjectionStore close failed: %s", exc)
      self._global_projection_store = None

  if self._idempotency_store is not None:
      try:
          self._idempotency_store.close()
          self._log_lifecycle("Phase1_store_closed", "IdempotencyStore")
      except Exception as exc:
          errors.append(exc)
          logger.warning("shutdown: IdempotencyStore close failed: %s", exc)
      self._idempotency_store = None

  # Per-session local stores are closed during destroy_session() —
  # add session.local_projection_store.close() in the P3 reverse
  # teardown section, after fabric shutdown.
  ```

**Per-session teardown addition** (in `destroy_session()`, after P3 fabric shutdown):

  ```python
  # Close per-session LocalProjectionStore
  local_store = getattr(session, "local_projection_store", None)
  if local_store is not None and hasattr(local_store, "close"):
      try:
          local_store.close()
      except Exception as exc:
          errors.append(exc)
          logger.warning(
              "destroy_session(%s): LocalProjectionStore close failed: %s",
              session_id, exc,
          )
  ```

**New KernelConfig fields:**

  ```python
  @dataclass
  class KernelConfig:
      # ... existing fields unchanged ...

      # Phase 1 store paths (defaults work for dev; override for production)
      global_projection_db_path: str = "./data/global_projection.db"
      idempotency_db_path: str = "./data/idempotency.db"
  ```

**Helper — `_get_native_provider()`:**

  ```python
  def _get_native_provider(fabric: Fabric) -> Any | None:
      """Extract NativeToolProvider from the Fabric's provider factory.
      Returns None if not yet registered (pre-S8)."""
      try:
          provider_factory = getattr(fabric.facade, "_resolver", None)
          if provider_factory is None:
              return None
          provider_registry = getattr(provider_factory, "provider_factory", None)
          if provider_registry is None:
              return None
          # NativeToolProvider is registered under provider_type="LOCAL"
          # in the provider factory's handler registry
          registry = getattr(provider_registry, "_provider_registry", None)
          if registry is None:
              return None
          from k1.fabric.providers.native_tool_provider import NativeToolProvider
          for handler in getattr(registry, "_handlers", {}).values():
              if isinstance(handler, NativeToolProvider):
                  return handler
          return None
      except Exception:
          logger.debug("_get_native_provider: not yet available", exc_info=True)
          return None
  ```

- **Risk:** Low. Isolated SQLite files. Shared store reference is read-only for per-session Fabric (writes happen only at bootstrap via `ManifestAdmissionService`). All existing kernel service tests unchanged — Phase 1 fields on `KernelConfig` have defaults, stores only open when `KernelConfig` paths are set.
- **Existing tests must pass:** All kernel service tests unchanged. Phase 1 stores are only created when the config paths are non-empty, which test configs don't set.
- **Verify:** `python -c "from k1.kernel.service import KernelService; from k1.concierge.config.kernel import KernelConfig; c = KernelConfig(); assert c.global_projection_db_path == './data/global_projection.db'"`

---

### Issue 7.4 — Tests

- **GAP-P1-021:** `tests/k1/fabric/test_fabric_wiring.py`
  - `TestFabricFieldsExist` — all 8 Phase 1 fields present on Fabric dataclass, all default to None
  - `TestMetaToolRegistered` — `resolve_situation` appears in meta-tool registry
  - `TestMetaToolHandlerReturnsErrorWhenNotWired` — calling `resolve_situation` with `situated_resolver=None` returns error envelope with `verdict='cannot_execute'`, `sub_reason='resolver_not_wired'`
  - `TestMetaToolHandlerDelegates` — with a mock situated_resolver, handler delegates and returns envelope.to_dict()
  - `TestBackwardCompatible` — creating Fabric without Phase 1 stores leaves all new fields as None

- **GAP-P1-022:** `tests/k1/fabric/test_factory_wiring.py`
  - `TestCreateSharedWithStores` — `create_shared(global_projection_store=...)` wires all components
  - `TestCreateSharedWithoutStores` — `create_shared()` without stores → all Phase 1 fields None, no crash
  - `TestCreateWithPortsWithLocalStore` — `create_with_ports(local_projection_store=...)` uses provided local store
  - `TestCreateWithPortsFallsBackToMemory` — no local store → creates `LocalProjectionStore(":memory:")` (not global store)
  - `TestConstitutionLoaderShared` — same `constitution_loader` instance used by both prompt_pack_builder and situated_resolver
  - `TestIdempotencyWiredToFacade` — `fabric.facade._idempotency_store` is set when `idempotency_store` provided
  - `TestVerificationRunnerNotWiredByFactory` — `fabric.verification_runner` is None after factory (kernel wires it later)
  - `TestResolveSituationServiceReceivesAllDeps` — all 8 optional deps passed to ResolveSituationService constructor

- **Run:** `pytest tests/k1/fabric/test_fabric_wiring.py tests/k1/fabric/test_factory_wiring.py -v`

---

### System Coherence: Epic 7 in Context

```
KernelService._startup_tier1()
│
├─ S1: Bus + Router
├─ S2: ModelHub
├─ S2.5–S2.9: HIL, SelfModel, Temporal, Spatial, Grounding
├─ S2.10: ─── GlobalProjectionStore.open() + IdempotencyStore.open() ─── NEW
├─ S4: Bridge
├─ S3: FabricFactory.create_shared(global_projection_store=..., idempotency_store=...)
│        └─ _construct_fabric() step 21:
│             • ConstitutionLoader(global) → shared
│             • LocalProjectionStore(":memory:") → per-session default
│             • ResolveResourcesService, CapabilityTypeResolver, PolicySelectorService,
│               CapabilityBinderService, PromptPackBuilder → per-session
│             • ResolveSituationService(all 8 deps) → per-session
│             • fabric.facade._idempotency_store = idempotency_store
│             • verification_runner = None (kernel wires after S8)
├─ S5: Orchestrator
├─ S6: Planner
├─ S6b: Cross-wire
├─ S7: Start Planner task
├─ S8: Family tools bootstrap
│
├─ Post-S8: ─── ManifestAdmissionService.admit_all(domain_catalog) ─── NEW
│              ─── VerificationPlanRunner(native_provider, global_store, constitution_loader) ─── NEW
│
└─ _running = True

KernelService._create_session_tier2()
│
├─ P1: Per-session Bus + Router
├─ P2: SessionState
├─ P3: FabricFactory.create_with_ports(
│        global_projection_store=shared,    ← shared reference
│        local_projection_store=LocalProjectionStore(":memory:"),  ← NEW per-session
│        idempotency_store=shared,          ← shared reference
│      )
│        └─ _construct_fabric() step 21:
│             • Same wiring as shared, but with per-session local_store
│             • Per-session ResolveSituationService with per-session local_store
├─ P4: Concierge
├─ P5: MemoryWriter
├─ P6: Register session
│
└─ SessionInstance (with .local_projection_store)

KernelService.shutdown()
│
├─ Destroy all sessions → each closes session.local_projection_store
├─ Reverse S8: family_tools.close()
├─ Reverse S3: shared_fabric.shutdown()
├─ ─── GlobalProjectionStore.close() ─── NEW
├─ ─── IdempotencyStore.close() ─── NEW
└─ Reverse S2–S1: ModelHub, Bus, Router
```

**Key invariants:**

1. `GlobalProjectionStore` is opened before Fabric and closed after Fabric.
2. `ConstitutionLoader` is created ONCE and shared between `PromptPackBuilder`, `ResolveSituationService`, and `VerificationPlanRunner`.
3. `LocalProjectionStore` is per-session — one `:memory:` instance per session, closed at session teardown.
4. `IdempotencyStore` is shared — all sessions check the same store for duplicate prevention.
5. `VerificationPlanRunner` is wired by the kernel (not the factory) because it needs `NativeProviderDispatch` which only exists after S8.
6. Domain catalog is loaded AFTER family tools bootstrap (S8) — connectors must be admitted AFTER the native provider is registered, so `NativeToolProvider` can serve verification readbacks.

---

## Epic 8: Integration Gate — Prove It All Works

**Goal:** Prove that every component from Epics 0–7 works in isolation AND together. This is the gate that must pass before Phase 1 is declared complete. No code changes happen in this Epic — it is purely verification.

**Design derivation from Epics 0–7:**

Every component in Epics 1–7 was designed with specific test files (GAP-P1-001 through GAP-P1-022). Those tests prove each component works in isolation. Epic 8 proves:

1. **Regression safety** — All 223 existing tests still pass. The new wiring (Epic 7) didn't break existing code paths.
2. **Component correctness** — All 17 new test files pass, covering every dataclass, every API method, every state machine transition, every verdict.
3. **POC parity** — The benchmark that drove the POC now drives the promoted code. Results must match or exceed.
4. **Integration coherence** — Smoke tests that span MULTIPLE epics prove the components actually compose.
5. **GATE-P1 checklist** — 14 acceptance criteria from the whiteboard, now updated to reference the actual typed components from Epics 1–7.

---

### Issue 8.1 — Regression Gate: Existing Test Suite

**Goal:** Prove that Epics 0–7 introduced zero regressions. Every existing test must pass.

- **Command:** `pytest tests/k1/fabric/ -v --timeout=120`
  - **Expected:** 113/113 pass — all existing fabric tests. The new `Fabric` dataclass fields (Epic 7.1) default to `None`. The factory step 21 is gated behind `if global_projection_store is not None`. No existing code path triggers the new wiring. No existing test should see any behavioral change.

- **Command:** `pytest tests/bridge/ -v`
  - **Expected:** 48/48 pass. Bridge is untouched by Phase 1.

- **Command:** `pytest tests/k1/tools/family/ -v`
  - **Expected:** 51/51 pass. Family tools still execute through `NativeToolProvider._execute()` → `ToolRegistry.get_service()` → `service.dispatch()`. The new `ToolDefinition` fields (Epic 9) are `Optional` with `default=None` — old code paths unchanged.

- **Command:** `pytest tests/k1/hil/ -v`
  - **Expected:** 11/11 pass. HIL service is untouched.

- **Command:** `pytest tests/k1/kernel/ -v`
  - **Expected:** All existing kernel service tests pass. Phase 1 stores are only created when `KernelConfig.global_projection_db_path` is non-empty, which test configs don't set.

- **Total:** 223 existing tests must pass. Zero regressions tolerated.

---

### Issue 8.2 — Component Gate: New Test Suite

**Goal:** Every new test file defined in Epics 1–7 passes. These are unit tests for individual components.

| GAP ID | Test File | Epic | Test Classes | What It Proves |
|--------|----------|------|-------------|----------------|
| GAP-P1-003 | `tests/k1/fabric/stores/test_global_projection_store.py` | 1 | 10 | 4 record dataclasses roundtrip, CRUD, FTS5 BM25, search by domain, resource kinds, constitutions, 5 graph ontology tables, 100K scale, manifest batch |
| GAP-P1-004 | `tests/k1/fabric/stores/test_local_projection_store.py` | 1 | 4 | Connected resources, household members, alias index, projection snapshots |
| GAP-P1-005 | `tests/k1/fabric/stores/test_idempotency_store.py` | 1 | 5 | State machine transitions, immutable succeeded, replay detection, TTL cleanup, concurrent access |
| GAP-P1-015 | `tests/k1/fabric/connectors/test_definitions.py` | 2 | 8 | ConnectorDefinition shape, builder generates all capabilities, read-only vs write, provider_id derivation, constitution defaults, ontology identity, all 50 connectors build, capability names unique |
| GAP-P1-016 | `tests/k1/fabric/resolver/test_request_frame.py` | 3 | 3 | BackTaskEnvelope parse/validate, RequestFrameBuilder from envelope, RequestFrame types frozen/serializable |
| GAP-P1-017 | `tests/k1/fabric/resolver/test_resource_projection.py` | 3 | 3 | Resolve person (exact, fuzzy, not_found, ambiguous), resolve resource (connected, direct, stale, readonly+write excluded), universe completeness |
| GAP-P1-018 | `tests/k1/fabric/resolver/test_capability_type_resolver.py` | 3 | 6 | Operation resolution, concept resolution, resource_family mapping, typed lookup, confidence scoring, E2E typed resolution |
| GAP-P1-002 | `tests/k1/fabric/policy/test_policy_selector.py` | 4 | 8 | Happy path, deny role, deny band, HIL trigger, protected read, default-allow, missing connector skip, verdict precedence |
| GAP-P1-006 | `tests/k1/fabric/verification/test_verification_runner.py` | 4 | 7 | Build plan, read_after_write success, mismatch, provider unavailable, output_schema, degraded completion, no constitution |
| GAP-P1-019 | `tests/k1/fabric/test_manifest_admission.py` | 4 | 8 | Valid admit, missing fields reject, batch admit, partial failure, idempotent, with constitution, with ontology, read-only connector |
| GAP-P1-008 | `tests/k1/fabric/constitution/test_constitution_schema.py` | 5 | 21 | Structural validation (8), semantic validation (6), sub-type roundtrip (4), coherence (3), ConstitutionLoader (8) |
| GAP-P1-020 | `tests/k1/fabric/resolver/test_capability_binder.py` | 6 | 14 | Typed intent binding, exact match, BM25 fallback, pass precedence, role propagation, companion discovery, prerequisite discovery, policy block, stale resource block, missing capability, binding dedup, tool selection commit, role separation, invocation_mode/effect mapping |
| GAP-P1-001 | `tests/k1/fabric/resolver/test_situated_resolver.py` | 6 | 14 | All 13 verdicts with sub-reason: happy path, can_execute_with_gate, missing_capability, blocked_by_policy, stale_projection, needs_disambiguation, missing_required_params, promote_to_tier3, cannot_execute, HIL gate triggered, conflict rule triggered, constitution loaded, idempotency enforced, full pipeline |
| GAP-P1-009 | `tests/k1/fabric/resolver/test_situated_resolver_negative.py` | 6 | 6 | Missing capability error, blocked by policy error, incomplete world projection, stale projection with refresh, budget exhausted, intent too vague |
| GAP-P1-011 | `tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py` | 6 | 12 | PromptPack shape, staged disclosure (8), redaction proof (8), constitution cards (5), tool name cards (4), policy cards (4), guide cards (4), schema cards (5), stale card policy (5), forbidden action gating (4), render budget (3), phase field whitelist (6) |
| GAP-P1-021 | `tests/k1/fabric/test_fabric_wiring.py` | 7 | 5 | Fabric fields exist, meta-tool registered, handler returns error when not wired, handler delegates, backward compatible |
| GAP-P1-022 | `tests/k1/fabric/test_factory_wiring.py` | 7 | 8 | Create shared with stores, create shared without stores, create with ports with local store, fallback to memory, constitution_loader shared, idempotency wired to facade, verification_runner not wired by factory, ResolveSituationService receives all deps |

**Run all new tests:**

```bash
pytest tests/k1/fabric/stores/ -v
pytest tests/k1/fabric/connectors/ -v
pytest tests/k1/fabric/resolver/ -v
pytest tests/k1/fabric/policy/ -v
pytest tests/k1/fabric/verification/ -v
pytest tests/k1/fabric/constitution/ -v
pytest tests/k1/fabric/prompt_pack/ -v
pytest tests/k1/fabric/test_fabric_wiring.py tests/k1/fabric/test_factory_wiring.py tests/k1/fabric/test_manifest_admission.py -v
```

**Expected:** All 17 test files pass. ~140 test classes. Zero failures.

---

### Issue 8.3 — POC Benchmark Parity

**Goal:** The promoted code must match or exceed the POC's benchmark results. The POC proved the approach works; the promoted code must prove it still works after the type cleanups, naming fixes, and whiteboard alignment.

- **Command:** `echo 2 | python scripts/probe_back_resolver_benchmark.py`
- **Metrics:**
  - Extraction pass rate: ≥ 96% (48/50 intents correctly resolve operation + resource_family)
  - Verdict pass rate: ≥ 92% (46/50 intents produce correct verdict)
  - Family domain: 100% all layers (extraction + verdict + binding)
  - Commit accuracy: ≥ 7/8 (Back selects correct capability from binding bundle)
     Canonical 8: F01 (family calendar create), F02 (family tasks list), F03 (family chores assign),
     E07 (enterprise on-call list), H02 (healthcare appointment book), H03 (healthcare lab order),
     A03 (agriculture field plan), G05 (government permit search).
- **Compare against:** `data/llm_frame_bench/results_resolver_vertex_gemini_2.5_flash_20260604_123800.json`
- **Regression tolerance:** None. Any metric that drops below the POC baseline is a blocker.
- **If benchmark is missing:** Run the POC benchmark first to establish baseline, then run the promoted benchmark. Save results to `data/llm_frame_bench/results_phase1_gate_*.json`.

---

### Issue 8.4 — Integration Smoke Tests (Cross-Epic)

**Goal:** Prove that components from DIFFERENT epics compose correctly. These are tests that span 2+ epics and cannot live in any single epic's test file because they require multiple components to be wired together.

- **GAP-P1-023:** `tests/k1/fabric/integration/test_pipeline_e2e.py`
  - `TestFullResolutionPipeline` — RequestFrame → ResourceUniverse → ResolvedIntentType → PolicyBundle → BindingBundle → ConstitutionArtifact → ResolutionEnvelope → PromptPack (spans Epics 3→4→5→6)
  - `TestMetaToolE2E` — `fabric._handle_resolve_situation(payload)` → `situated_resolver.resolve()` → `ResolutionEnvelope` with correct verdict (spans Epics 6→7)
  - `TestDomainCatalogLoad` — `build_domain_corpus("family")` → `ManifestAdmissionService.admit_all()` → `GlobalProjectionStore` has 10 connectors, each with ≥4 capabilities (spans Epics 2→4→1)
  - `TestStoreIsolation` — Global store write → NOT visible in per-session LocalProjectionStore. Shared store read → visible from per-session fabric (spans Epics 1→7)
  - `TestIdempotencyEnforcementE2E` — First `resolve_situation` with idempotency_key X → `can_execute`. Second `resolve_situation` with same key → `cannot_execute` with `sub_reason='idempotency_duplicate'` (spans Epics 1→6→7)
  - `TestConstitutionRejection` — Bad constitution (missing `execution_phases`) → `ManifestAdmissionService.admit()` returns `admission_verdict='rejected'` (spans Epics 5→4)
  - `TestRedactionProofE2E` — Build PromptPack with source containing `RESTRICTED:` marker → `PromptPackLeakError` (spans Epic 6)
  - `TestVerificationPlanE2E` — Execute write → `VerificationPlanRunner.build_plan()` → `run()` → `VerificationObservation(status='verified')` (spans Epics 4.2→5→1)

- **Run:** `pytest tests/k1/fabric/integration/ -v`

---

### Issue 8.5 — GATE-P1 Checklist

**Goal:** 14 acceptance criteria from the whiteboard §Phase 1 integration gate, updated to reference the actual typed components. Every box must be checked.

```text
□ [GATE-01] All 41+ family-tool capability contracts registered and discoverable
     → GlobalProjectionStore.count_capabilities() ≥ 41 for family domain.
     → search_capabilities("calendar", top_k=5) returns family.calendar capabilities.

□ [GATE-02] resolve_situation returns ResolutionEnvelope with valid ResourceUniverse
     → ResolutionEnvelope.resource_universe is not None.
     → resource_universe.resource_candidates has ≥1 ResourceCandidate with connector_id set.

□ [GATE-03] CapabilityBinderService.bind() produces primary binding for calendar create
     → BindingBundle.primary.capability_name == "tool.execute.family.calendar.create".
     → BindingBundle.prerequisites has list binding for prerequisite_reads.

□ [GATE-04] NativeToolProvider dispatches to correct adapter service
     → CapabilityFabric.execute(request with capability_name="tool.execute.family.calendar.create")
       invokes CalendarToolService.dispatch().

□ [GATE-05] Bridge ConnectorGateway validates tokens and routes to adapter
     → (Deferred to Phase 2 — Bridge integration is out of Phase 1 scope.
        Phase 1 is Fabric-standalone. GATE-P1 does not require live K0 bridge.)

□ [GATE-06] IdempotencyStore prevents duplicate execution
     → First capability execution with idempotency_key X → success.
     → Second execution with same key → idempotency_blocked.

□ [GATE-07] VerificationPlanRunner.read_after_write confirms event exists after create
     → After calendar.create_event, build_plan() returns plan with verifier_method='read_after_write'.
     → run(plan) returns VerificationObservation(status='verified').

□ [GATE-08] PolicySelectorService returns PolicyBundle with gates for calendar write
     → select(universe, intent_types, "parent", "GREEN") → policy_verdict='allow'.
     → select(universe, intent_types, "child", "GREEN") → policy_verdict='allow' (default-allow).
     → select(universe, intent_types, "guest", "AMBER") →
       (policy_verdict='deny' OR any gate has gate_type='safety_band' AND action_required='deny').

□ [GATE-09] HIL service fires hil.request on missing_required_params
     → resolve_situation with intent lacking required params (no title, no time) →
       verdict='missing_required_params' or 'needs_hil' (depends on constitution HIL gates).

□ [GATE-10] discover_capabilities returns catalog results (legacy path)
     → fabric.discover_capabilities(domain=["family"], intent="calendar") returns results.
     → (Phase 1 does not change discover_capabilities — it adds resolve_situation as a NEW path.)

□ [GATE-11] All adapter ports satisfy their protocol types
     → isinstance(fabric.facade, CapabilityFabric) is True.
     → isinstance(fabric.global_projection_store, GlobalProjectionStore) is True when wired.
     → isinstance(fabric.situated_resolver, ResolveSituationService) is True when wired.

□ [GATE-12] Negative proof: invalid params → resolution fails with sub_reason
     → resolve_situation with intent that has no subject_hint, no params, no time_window →
       verdict='missing_required_params', sub_reason='intent_too_vague'.

□ [GATE-13] Negative proof: AMBER safety band → policy gates appropriately
     → PolicySelector.select() with safety_band='AMBER' and an operation requiring 'GREEN' →
       policy gates reflect the band mismatch (verdict='deny' or gate with action_required='deny').

□ [GATE-14] Negative proof: missing connector → missing_capability verdict
     → resolve_situation with resource_kind that has no connector in GlobalProjectionStore →
       verdict='missing_capability', sub_reason includes resource_kind.
```

**GATE-P1 checklist automation** (GAP-P1-023, `TestGateChecklist`):

- Each GATE item above has a corresponding test method: `test_gate_01` through `test_gate_14`.
- Tests are self-checking — they assert the exact expected value, not a human-readable description.
- GATE-05 is `@pytest.mark.skip(reason="Phase 2 — Bridge integration")`.
- Running `pytest tests/k1/fabric/integration/test_pipeline_e2e.py::TestGateChecklist -v` must produce 13 passed, 1 skipped.

---

### Issue 8.5 — Documentation Update: Align 3 External Docs to Phase 1 Design

**Goal:** Update the three connector documentation files to reflect the actual typed components, naming conventions, and design decisions established in Epics 1–8. These docs are the public-facing API surface — they must not reference stale field names or pre-Epic concepts.

**Design derivation:** Each doc update is driven by a specific Epic's design decision. The table below traces every change to its Epic source.

| Doc Section | Current Text | Change | Epic Source |
|-------------|-------------|--------|-------------|
| **connector_development_external.md** | | | |
| §2 IFL manifest `capability_templates[].operation: "list"/"create"` | `operation: "list"` | Replace with `invocation_mode: "read"` + `action_name: "list"` | Epic 1.2: `operation` → `invocation_mode` + `action_name` |
| §4 constitution `mutation_sequencing[].order/operation` | Only `order` + `operation` | Add `phase` field: `phase: "read"` / `phase: "mutate"` | Fix 4: `MutationStep.phase` must match `execution_phases` |
| §4 constitution summary fields | `precondition_sum`, `companion_resource_sum`, `hil_trigger_sum` | Rename to `precondition_summary`, `companion_resource_summary`, `hil_trigger_summary` | Epic 5.1: `ConstitutionArtifact` field names |
| §1 Kernel Provides table | 13 components listed | Add `ConstitutionLoader` (validates + loads constitutions), `ResolveResourcesService` (resolves person/entity aliases) | Epic 5.2, Epic 3.4 |
| Appendix A naming convention | `tool.{effect_type}.{domain}.{connector}.{action}` | Update to `tool.{invocation_mode}.{domain}.{connector}.{action_name}` | Epic 2.3 capability naming |
| §4.2 Admission checklist | `ContractValidator: JSON Schema + 12 semantic rules` | Reference `CONSTITUTION_JSON_SCHEMA` (Draft-07, Epic 5.1) + `validate_constitution()` + `validate_constitution_semantics()` | Epic 5.1 |
| **connector_onboarding_familyos.md** | | | |
| §1.2 capability fields | `operation: "create"`, `effect: "write"` | Replace with `invocation_mode: "execute"`, `action_name: "create"`, `effect: "write"` | Epic 1.2: split `operation` into `invocation_mode` + `action_name` |
| §1.2 required fields list | `operation` as required | List `invocation_mode` + `action_name` as required instead | Epic 1.2 |
| §1.1 connector fields | `connector_type: "native_local"` | Change to `"native"` | Epic 1.2 SQL: `CHECK(connector_type IN ('native','bridge','ifl'))` |
| §1.1 connector fields | `registration_type: "executable"` | Change to `"executable_capability"` | Epic 1.2 SQL: `CHECK(record_type IN ('executable_capability','activity_profile','workflow','agent'))` |
| §1.2 capability naming | `tool.{effect_type}.{domain}.{connector}.{action}` | Update to `tool.{invocation_mode}.{domain}.{connector}.{action_name}` | Epic 2.3 |
| §1.3 constitution summary fields | `precondition_sum`, `companion_resource_sum`, `hil_trigger_sum` | Rename to `precondition_summary`, `companion_resource_summary`, `hil_trigger_summary` | Epic 5.1 |
| §1.3 mutation_sequencing | `order` + `operation` only | Add `phase` field per `MutationStep` dataclass | Fix 4 |
| §1.2 risk_class values | `"write"`, `"read_only"` | Align with `CapabilityRecord.risk_class` default `"benign"`; use `"benign"`, `"sensitive"`, or `"dangerous"` | Epic 1.1 |
| **fabric_integration_guide.md** | | | |
| Deprecation banner | `being promoted from POC to k1/fabric/` | Replace with `Phase 1 design complete (Epics 0–8). Implementation-ready.` | Epics 0-8 complete |
| Migration status | Lists component names from early POC | Update to final typed names: `ConstitutionArtifact`, `ResolvedIntentType`, `BindingBundle` (with role separation), `ResolutionEnvelope` (13 verdicts), `PromptPack` (5 phases, redaction-proof) | Epics 3-6 |
| Target model line | `resolve_situation → BindingBundle → invoke_capability by binding_id` | Expand to full chain: `ConnectorDefinition → ManifestAdmissionService → GlobalProjectionStore → RequestFrame → ResolveSituationService (13-step cascade) → ResolutionEnvelope {verdict, BindingBundle, ConstitutionArtifact, PolicyBundle, PromptPack}` | Epics 2→4→1→3→6 |
| What changes section | `RetrievalEngine vector search → ResolveSituationService` | Clarify: `discover_capabilities` (legacy, unchanged) + `resolve_situation` (NEW Phase 1 path — typed graph + exact match + BM25 via 3-pass CapabilityBinder) | Epic 6.1 |
| References | Lists 3 target docs | Add `k1/fabric/docs/phase1_implementation_plan.md` — the full Epic-level specification | This document |

**Files to update:**

| File | Sections Touched | Risk |
|------|-----------------|------|
| `k1/fabric/docs/connector_development_external.md` | §1 (Kernel Provides), §2 (IFL manifest, constitution), §4 (admission checklist), Appendix A (naming), Appendix C (schemas) | Low — docs only, no code dependencies |
| `k1/fabric/docs/connector_onboarding_familyos.md` | §1.1 (connector fields), §1.2 (capability fields + naming), §1.3 (constitution), §1.4 (policy) | Low — docs only |
| `k1/fabric/docs/fabric_integration_guide.md` | Deprecation banner, migration status, target model, what changes, references | Low — docs only |

**Verify:**

- `python -c "import yaml; d = yaml.safe_load(open('k1/fabric/docs/connector_onboarding_familyos.md')); ..."` — not applicable (markdown docs, not executable)
- Manual review: every field name in these docs matches the dataclass field names in Epics 1–7.
- Cross-reference: `connector_development_external.md` §1 Kernel Provides table has the same component names as `phase1_implementation_plan.md` Epic summaries.
- Cross-reference: `connector_onboarding_familyos.md` §1.2 capability naming matches `builder.py` capability naming convention from Epic 2.3.

---

### Issue 8.6 — Final Inventory: All Tests

**Complete test inventory after Phase 1:**

| Category | Count | Details |
|----------|-------|---------|
| Existing fabric tests | 113 | `tests/k1/fabric/` — unchanged |
| Existing bridge tests | 48 | `tests/bridge/` — unchanged |
| Existing family tool tests | 51 | `tests/k1/tools/family/` — unchanged |
| Existing HIL tests | 11 | `tests/k1/hil/` — unchanged |
| New unit tests (all Epics) | ~140 test classes | GAP-P1-001 through GAP-P1-022 (17 test files) |
| New integration tests | 8 test classes | GAP-P1-023 (`test_pipeline_e2e.py`) |
| GATE-P1 checklist tests | 14 methods | `TestGateChecklist` in GAP-P1-023 |
| **Total** | **~385** | **223 existing + ~162 new** |

**Files created across Epics 0–7:**

| Epic | New Files |
|------|----------|
| 0 — Scaffold | 7 `__init__.py` |
| 1 — Stores | 3 (`global_projection_store.py`, `local_projection_store.py`, `idempotency_store.py`) |
| 2 — Connectors | 3 (`definition.py`, `builder.py`, `domain_catalog.py`) |
| 3 — Resolver | 5 (`back_task_envelope.py`, `request_frame.py`, `request_frame_builder.py`, `resource_projection.py`, `capability_type_resolver.py`) |
| 4 — Governance | 3 (`policy/selector.py`, `verification/runner.py`, `manifest_admission.py`) |
| 5 — Constitution | 2 (`constitution/schema.py`, `constitution/loader.py`) |
| 6 — Orchestration | 3 (`resolver/capability_binder.py`, `resolver/situated_resolver.py`, `prompt_pack/builder.py`) |
| 7 — Wiring | 0 (modifies 3 existing files) |
| 8 — Gate | 1 (`tests/k1/fabric/integration/test_pipeline_e2e.py`) |
| **Total** | **27 new Python files** |

**Files modified:**

| File | Epic | Risk |
|------|------|------|
| `k1/fabric/fabric.py` | 7.1 | Zero — new fields default to None, new meta-tool is additive |
| `k1/fabric/factory.py` | 7.2 | Zero — step 21 gated behind `if global_projection_store is not None` |
| `k1/kernel/service.py` | 7.3 | Low — new S2.10 step, store lifecycle, domain catalog load |

**Files NOT touched (zero risk):**

30+ files — `fabric.py:_execute_impl()` (except `_idempotency_store` attribute set), `core/registry.py`, `provider_resolution/`, `providers/` (except `NativeToolProvider` used by verifier), `policy/` (PolicyEngine — distinct from PolicySelectorService), `retrieval/`, `context/`, `circuit_breaker/`, `output_validation/`, `contracts/`, `module_registry/`, `events/`, `adapters/`, `concurrency/`, `health/`, `manifest_translator.py`, `types.py`, all of `bridge/`, all of `k1/concierge/`, all of `k1/tools/family/` (except `definition.py` optional field additions in Epic 9).

---

### System Coherence: The Full Phase 1 Pipeline

```
                          ┌──────────────────────┐
                          │    Back (LLM Actor)    │
                          │  Extracts intents,      │
                          │  calls resolve_situation│
                          └──────────┬─────────────┘
                                     │ meta-tool: resolve_situation
                                     ▼
                          ┌──────────────────────┐
                          │  Fabric._handle_      │  Epic 7.1
                          │  resolve_situation()  │
                          └──────────┬─────────────┘
                                     │ ResolveSituationRequest
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   ResolveSituationService.resolve()                  │  Epic 6.2
│                      13-step verdict cascade                         │
│                                                                      │
│  Step 1-2: Budget + Idempotency (Epic 1.6)                          │
│  Step 3-6: ResourceUniverse + ambiguous/stale checks (Epic 3.4)     │
│  Step 7:   Intent too vague check (Epic 3.2)                        │
│  Step 8:   Promote to Tier 3 (Epic 6.2 binding analysis)            │
│  Step 9:   PolicySelectorService.select() → PolicyBundle (Epic 4.1) │
│  Step 10:  Stale binding check (Epic 6.1 BindingBundle)             │
│  Step 11:  Missing capability check (Epic 6.1 BindingBundle)        │
│  Step 12:  ConstitutionLoader.load() → prerequisite check (Epic 5)  │
│  Step 13:  HIL gate check (Epic 5.1 HILGate)                        │
│                                                                      │
│  Sub-components:                                                     │
│    ResolveResourcesService (Epic 3.4) → ResourceUniverse             │
│    CapabilityTypeResolver (Epic 3.5) → list[ResolvedIntentType]      │
│    CapabilityBinderService (Epic 6.1) → BindingBundle                │
│    ConstitutionLoader (Epic 5.2) → ConstitutionArtifact              │
│    PromptPackBuilder (Epic 6.3) → PromptPack                         │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ ResolutionEnvelope {verdict, prompt_pack, ...}
                       ▼
              ┌──────────────────────┐
              │    Back receives      │
              │  ResolutionEnvelope   │
              │  .verdict → action    │
              │  .prompt_pack → LLM   │
              │  .allowed_capability_ │
              │    names → tool choice│
              └──────────────────────┘
```

**Data stores backing the pipeline:**

```
GlobalProjectionStore (Epic 1.1-1.4) — shared, SQLite WAL
  ├─ capabilities (13 columns, FTS5-indexed)
  ├─ connectors (12 columns)
  ├─ resource_kinds
  ├─ connector_constitutions (17 JSON columns)
  ├─ concept_aliases, concept_resource_edges, resource_connector_edges
  ├─ operation_equivalences, operation_aliases
  └─ capability_type_index

LocalProjectionStore (Epic 1.5) — per-session, SQLite
  ├─ connected_resources
  ├─ household_members
  ├─ alias_index
  └─ resource_projection_snapshots

IdempotencyStore (Epic 1.6) — shared, SQLite
  └─ idempotency_keys (state machine: not_seen → in_flight → succeeded/failed)
```

**What GATE-P1 passing MEANS:**

1. `GlobalProjectionStore` has 50 connectors × ~5 capabilities each = ~250 capabilities, all discoverable via FTS5 BM25 search.
2. `ResolveSituationService.resolve()` processes a `RequestFrame` through all 13 steps and returns a `ResolutionEnvelope` with the correct verdict and sub-reason.
3. `CapabilityBinderService.bind()` finds the right capability using typed graph resolution (not keyword guessing).
4. `PolicySelectorService.select()` gates on typed intents (`ResolvedIntentType`), not loose operation strings.
5. `ConstitutionLoader.load()` returns a typed `ConstitutionArtifact` with validated sub-types — enforced by JSON Schema + semantic rules.
6. `PromptPackBuilder.build()` produces a redaction-proof `PromptPack` with 5 disclosure phases.
7. `IdempotencyStore` blocks duplicate execution across ALL sessions.
8. `VerificationPlanRunner` confirms writes via `read_after_write`.
9. The `resolve_situation` meta-tool is registered and callable from Back.
10. All 223 existing tests pass — zero regressions.
11. Benchmark matches or exceeds POC results.
12. 14 GATE-P1 checklist items pass (13 automated + 1 deferred).

---

## Summary — Phase 1 (Epics 0–8): Fabric Standalone

| Epic | Issues | Files Created | Files Modified | Tests |
|------|--------|--------------|----------------|-------|
| 0 — Scaffold | 1 | 7 `__init__.py` | 0 | 0 |
| 1 — Stores | 7 | 3 (global, local, idempotency) | 0 | GAP-003,004,005 |
| 2 — Connectors | 5 | 3 (definition, builder, catalog) | 0 | GAP-015 |
| 3 — Resolver | 6 | 5 (envelope, frame, builder, projection, type_resolver) | 0 | GAP-016,017,018 |
| 4 — Governance | 3 | 3 (policy, verification, admission) | 0 | GAP-002,006,019 |
| 5 — Constitution | 2 | 2 (schema, loader) | 0 | GAP-008 |
| 6 — Orchestration | 4 | 3 (binder, situated, prompt) | 0 | GAP-001,009,011,020 |
| 7 — Wiring | 4 | 0 | 3 (fabric.py, factory.py, service.py) | GAP-021,022 |
| 8 — Gate | 7 | 1 (integration test) + 3 docs updated | 0 | GAP-023 + all 223 existing |
| **Total** | **39** | **27 new files** | **3 modified** | **~250 tests (18 new + 223 existing)** |

**Files NOT touched (zero risk):** 30+ files — `fabric.py:_execute_impl()` (except `_idempotency_store` attribute set), `core/registry.py`, `provider_resolution/`, `providers/` (except `NativeToolProvider` used by verifier), `policy/` (PolicyEngine — distinct from PolicySelectorService), `retrieval/`, `context/`, `circuit_breaker/`, `output_validation/`, `contracts/`, `module_registry/`, `events/`, `adapters/`, `concurrency/`, `health/`, `manifest_translator.py`, `types.py`, all of `bridge/`, all of `k1/concierge/`, all of `k1/tools/family/`.

**GATE-P1 passing means:** All 223 existing tests pass. All 18 new test files (GAP-P1-001 through GAP-P1-023) pass. POC benchmark matches or exceeds. The 14 GATE-P1 checklist items are verified (13 automated, 1 deferred). Fabric is standalone-proven — `resolve_situation` returns correct verdicts, `BindingBundle` has typed bindings, `ConstitutionLoader` returns validated artifacts, `PromptPackBuilder` produces redaction-proof packs.

---

# Phase 1.1 — Family Tool Constitution Enrichment

> **Milestone:** GATE-P1.1 — Family tools enriched with full constitutions, policies, guide cards, ontology, and JSON schemas.
> **Predecessor:** Phase 1 (GATE-P1 must pass first)
> **Successor:** Phase 2 — Back
> **Scope:** Epics 9–14. Touches existing family tool definitions, retrieval, context builder, and activity profiles. Risk class is higher than Phase 1 because existing tool execution paths are modified.

---

## Epic 9: Calendar Connector — Full API Design

**Goal:** Upgrade the calendar family tool from the current `ToolDefinition`/`ActionSpec` model to the complete connector API defined in `connector_onboarding_familyos.md`. Calendar is the reference implementation — get it right, then replicate for tasks/reminders/chores/shopping.

**Why not a generic sync:** The API gap is too large for a mechanical `sync_registry_to_store()`. `ToolDefinition` has zero constitution fields, zero policy declarations, zero guide cards, zero ontology edges, and `FieldSpec` is intentionally narrower than JSON Schema. Skeleton records with empty constitutions don't pass GATE-P1. Each tool needs a proper design pass.

**Source of truth for target API:** `k1/fabric/docs/connector_onboarding_familyos.md` §1.1–§1.6

### Issue 9.1 — Add Constitution + Policy + Guide Cards + Ontology to ToolDefinition

- **File:** `k1/tools/family/definition.py`
- **What:** Add optional fields to `ToolDefinition`:

  ```python
  class ToolDefinition(BaseModel):
      # ... existing 19 fields unchanged ...

      # NEW Phase 1 fields (all Optional — backward compatible):
      constitution: Optional[dict[str, Any]] = Field(
          default=None,
          description="Connector constitution artifact. See connector_onboarding_familyos.md §1.3."
      )
      policy_declarations: Optional[dict[str, Any]] = Field(
          default=None,
          description="Per-connector policy rules. See connector_onboarding_familyos.md §1.4."
      )
      guide_cards: Optional[list[dict[str, Any]]] = Field(
          default=None,
          description="LLM-facing guidance cards. See connector_onboarding_familyos.md §1.5."
      )
      ontology: Optional[dict[str, Any]] = Field(
          default=None,
          description="Domain ontology registration. See connector_onboarding_familyos.md §1.6."
      )
      resource_kinds: Optional[list[str]] = Field(
          default=None,
          description="Multiple resource kinds (overrides singular entity_type for the store)."
      )
      actor_scope: Optional[list[str]] = Field(
          default=None,
          description="Roles that can use this connector. Defaults to ['parent','admin','system']."
      )
  ```

- **Also:** Add `input_schema` + `output_schema` (full JSON Schema dicts) to `ActionSpec` as optional fields alongside the existing skinny `params`/`result` `FieldSpec` lists. When present, these are used for `GlobalProjectionStore`. When absent, `FieldSpec` remains the source.
- **Backward compatibility:** All existing family tools continue to work with `FieldSpec`. New fields are `Optional` with `default=None`. Old code paths unchanged.
- **Verify:** `python -c "from k1.tools.family.definition import ToolDefinition; assert hasattr(ToolDefinition, 'model_fields')"`

### Issue 9.2 — Write Full Calendar Connector Manifest

- **File:** `k1/tools/family/calendar/definition.py`
- **What:** Populate ALL new fields on `CALENDAR_DEFINITION`:
  - `resource_kinds: ["calendar_event", "appointment"]` (was singular `entity_type`)
  - `actor_scope: ["parent", "admin", "system"]`
  - `constitution:` — full constitution (see below)
  - `policy_declarations:` — policy rules (see below)
  - `guide_cards:` — migrate from `k1/contracts/prompts/calendar_activity_v1.yaml`
  - `ontology:` — concept aliases + edges (see below)
  - Each `ActionSpec` gets `input_schema` + `output_schema` (full JSON Schema dicts)

### Issue 9.3 — Calendar Constitution

- **What:** Write the `constitution` block. This is the most important artifact — it tells the resolver WHAT to enforce.

  ```yaml
  constitution:
    connector_id: "family.calendar"
    constitution_id: "family.calendar.v1"
    schema_version: "1.0.0"
    execution_phases: ["read", "mutate"]
    prerequisite_reads:
      - operation: "list"
        resource_kind: "calendar_event"
        reason: "Check for time-window conflicts before creating or updating events."
        required: true
        timeout_ms: 5000
    conflict_analysis_rules:
      - check: "time_overlap"
        with_resource_kinds: ["calendar_event", "chore", "task"]
        description: "New event must not overlap existing events, chores, or tasks."
      - check: "participant_availability"
        description: "All attendees must be free in the target time window."
    companion_resource_roles:
      - resource_kind: "chore"
        role: "conflict_source"
      - resource_kind: "task"
        role: "conflict_source"
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
        prompt: "Which person did you mean?"
    mutation_sequencing:
      - order: 1
        phase: "read"
        operation: "list"
        description: "Read current calendar state before mutating."
      - order: 2
        phase: "mutate"
        operation: "create"
        description: "Create the event if no conflicts detected."
      - order: 3
        phase: "read"
        operation: "list"
        description: "Verify event was created (read_after_write)."
    verification_requirements:
      - method: "read_after_write"
        required_for_submit: true
      - method: "output_schema"
    precondition_summary: "List calendar before creating events to check for time conflicts."
    companion_resource_summary: "Calendar conflicts with chores and tasks in the same time window."
    hil_trigger_summary: "HIL required when end time or calendar is missing, or when a time conflict exists."
    degradation_policy: "If read_after_write verification fails, retry once then submit degraded."
  ```

### Issue 9.4 — Calendar Policy Declarations

- **What:** Write `policy_declarations`:

  ```yaml
  policy_declarations:
    write_requires_actor_role: []           # default-allow
    read_allowed_roles: []
    protected_resources:
      - resource_id_pattern: "cal_parent_*"
        reason: "Parent calendar contains sensitive appointments."
        required_role: "parent"
    hil_triggers:
      - condition: "write_operation AND actor_role == 'child'"
        prompt: "Ask a parent to confirm this calendar change."
  ```

### Issue 9.5 — Calendar Guide Cards

- **What:** Migrate `k1/contracts/prompts/calendar_activity_v1.yaml` into `ToolDefinition.guide_cards`:

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

- **Also:** The `compatible_tools` list from the old `calendar_activity_v1.yaml` becomes a constitution rule (already in §9.3 constitution above). The `activity_profile` field moves from `prompt_contract` to `ToolDefinition.activity_profile`.

### Issue 9.6 — Calendar Domain Ontology

- **What:** Write `ontology` block registering concept aliases, resource edges, and operation aliases:

  ```yaml
  ontology:
    domain: "family"
    concept_aliases:
      - {alias: "dentist", canonical_concept: "appointment", weight: 0.9}
      - {alias: "doctor", canonical_concept: "appointment", weight: 0.9}
      - {alias: "practice", canonical_concept: "calendar_event", weight: 0.7}
      - {alias: "game", canonical_concept: "calendar_event", weight: 0.7}
      - {alias: "recital", canonical_concept: "calendar_event", weight: 0.8}
      - {alias: "calendar event", canonical_concept: "calendar_event", weight: 1.0}
    concept_resource_edges:
      - {concept: "appointment", resource_family: "calendar_event", weight: 1.0}
      - {concept: "calendar_event", resource_family: "calendar_event", weight: 1.0}
    resource_connector_edges:
      - {resource_family: "calendar_event", connector_id: "family.calendar", weight: 1.0, role: "primary"}
    operation_equivalences:
      - {canonical_operation: "list", equivalent_operation: "search", resource_family: "calendar_event"}
    operation_aliases:
      - {alias: "schedule", operation_family: "create", effect: "write"}
      - {alias: "book", operation_family: "create", effect: "write"}
      - {alias: "add", operation_family: "create", effect: "write"}
  ```

### Issue 9.7 — Calendar Full JSON Schemas

- **What:** Add `input_schema` + `output_schema` (full JSON Schema Draft-07 dicts) to each `ActionSpec` in `CALENDAR_DEFINITION`. The existing `params`/`result` `FieldSpec` lists stay as the skinny fallback.
- **Example for `create_event`:**

  ```python
  ActionSpec(
      name="create_event",
      kind="write",
      params=[...],  # existing skinny FieldSpec — stays
      input_schema={  # NEW full JSON Schema
          "type": "object",
          "properties": {
              "title": {"type": "string", "minLength": 1, "maxLength": 200},
              "start": {"type": "string", "format": "date-time"},
              "end": {"type": "string", "format": "date-time"},
              "resource_id": {"type": "string"},
              "idempotency_key": {"type": "string"},
              "notes": {"type": "string"},
              "location": {"type": "string"},
              "attendees": {"type": "array", "items": {"type": "string"}},
          },
          "required": ["title", "start", "end", "resource_id", "idempotency_key"],
          "additionalProperties": False,
      },
      output_schema={  # NEW
          "type": "object",
          "properties": {
              "event_id": {"type": "string"},
              "status": {"enum": ["created", "conflict", "blocked"]},
          },
          "required": ["event_id", "status"],
      },
  )
  ```

### Issue 9.8 — ManifestTranslator Extension: Populate GlobalProjectionStore

- **File:** `k1/fabric/manifest_translator.py`
- **What:** Add `register_definition_to_store(definition: ToolDefinition, store: GlobalProjectionStore) -> int` that:
  1. Builds `ConnectorRecord` from `ToolDefinition` (all 14 fields now populated from the new optional fields)
  2. For each `ActionSpec`: builds `CapabilityRecord` using `input_schema`/`output_schema` when present (falling back to `FieldSpec` when absent)
  3. Upserts `ConstitutionRecord` if `constitution` is present
  4. Seeds graph ontology tables if `ontology` is present
  5. Returns count of capabilities registered
- **Key:** The existing `register_definition(definition, registry)` that populates `CapabilityRegistry` is UNCHANGED. This is an ADDITIONAL path that also populates `GlobalProjectionStore`.

### Issue 9.9 — Wire Into bootstrap_family_tools

- **File:** `k1/tools/family/registry.py` — `ToolRegistry.register_class()`
- **What:** After `register_definition(svc.DEFINITION, fabric.registry)` (existing line), add:

  ```python
  # NEW Phase 1: Also register in GlobalProjectionStore if available
  gps = getattr(fabric, 'global_projection_store', None)
  if gps is not None:
      from k1.fabric.manifest_translator import register_definition_to_store
      register_definition_to_store(svc.DEFINITION, gps)
  ```

- **This means:** When `bootstrap_family_tools()` runs at S8, each tool is registered in BOTH `CapabilityRegistry` (in-memory, for `NativeToolProvider`) AND `GlobalProjectionStore` (SQLite, for `ResolveSituationService`). No separate sync step needed.

### Issue 9.10 — Calendar E2E: resolve_situation Works

- **Test:** With full constitution + policy + ontology + schemas, `resolve_situation` for "Add dentist appointment for Riley next Monday at 3pm" returns `can_execute` with `tool.execute.family.calendar.create` as primary binding, constitution prerequisite_reads enforced (list before create), conflict_analysis_rules active, HIL gates on missing fields.
- **Run:** Part of GAP-P1-001 (`test_situated_resolver.py`)
- **Also:** `pytest tests/k1/tools/family/calendar/ -v` — all 10+ existing calendar tests still pass.

---

## Epic 10: Tasks Connector — Full API Design

**Goal:** Upgrade the tasks family tool with full constitution, policy, guide cards, ontology, and JSON schemas. Follows the calendar pattern (Epic 9) with task-specific rules.

**Design derivation from Epics 1–8:**

- Constitution follows `ConstitutionArtifact` schema (Epic 5.1) — validatable by `CONSTITUTION_JSON_SCHEMA`
- `MutationStep` includes `phase` field (Fix 4)
- `resource_connector_edges` include `role` (Epic 1.2)
- Capability naming: `tool.{invocation_mode}.family.tasks.{action_name}` (Epic 2.3)
- Policy gated on `ResolvedIntentType` (Epic 4.1, Fix 7)
- Registered via `register_definition_to_store()` at `bootstrap_family_tools()` (Epic 9.8-9.9)

### Issue 10.1 — Tasks Constitution (YAML)

```yaml
constitution:
  connector_id: "family.tasks"
  constitution_id: "family.tasks.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]
  prerequisite_reads:
    - operation: "list"
      resource_kind: "task"
      reason: "Check for duplicate tasks before creating."
      required: true
      timeout_ms: 5000
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["task"]
      description: "New task title must not match an existing open task for the same assignee."
  companion_resource_roles: []
  hil_gates:
    - trigger: "missing_required_field"
      field: "title"
      prompt: "What should the task be called?"
    - trigger: "missing_required_field"
      field: "assignee"
      prompt: "Who should this task be assigned to?"
    - trigger: "ambiguous_person"
      prompt: "Which person did you mean?"
  mutation_sequencing:
    - order: 1, phase: "read", operation: "list", description: "Read current task list before mutating."
    - order: 2, phase: "mutate", operation: "create", description: "Create the task if no duplicate detected."
    - order: 3, phase: "read", operation: "list", description: "Verify task was created (read_after_write)."
  verification_requirements:
    - method: "read_after_write"
      required_for_submit: true
    - method: "output_schema"
  precondition_summary: "List tasks before creating to check for duplicates."
  companion_resource_summary: null
  hil_trigger_summary: "HIL required when task title or assignee is missing."
  degradation_policy: "If read_after_write verification fails, retry once then submit degraded."
```

### Issue 10.2 — Tasks Policy + Guide Cards + Ontology

- **Policy:** `write_requires_actor_role: []` (default-allow), `read_allowed_roles: []`, no protected resources, no HIL triggers.
- **Guide cards:** Migrate `k1/contracts/prompts/tasks_activity_v1.yaml` → `ToolDefinition.guide_cards`. Include task management guidance: list before create, assign explicitly, use priority hints.
- **Ontology:** `concept_aliases`: "todo"→"task", "homework"→"task", "errand"→"task". `resource_connector_edges`: `{resource_family: "task", connector_id: "family.tasks", role: "primary"}`. `operation_equivalences`: `{canonical: "list", equivalent: "search"}`. `operation_aliases`: "assign"→update, "complete"→update, "finish"→update, "add"→create.
- **JSON Schemas:** Add `input_schema` + `output_schema` (Draft-07) to all `ActionSpec` entries in `TASKS_DEFINITION`.

### Issue 10.3 — Tasks Tests

- **GAP-P1-024:** `tests/k1/fabric/connectors/test_family_tasks.py`
  - `TestConstitutionValidates` — tasks constitution passes `validate_constitution()`
  - `TestResolveSituationTaskIntent` — "add homework for Riley due Friday" → `can_execute` with `tool.execute.family.tasks.create` as primary
  - `TestDuplicateTaskBlocked` — same title + assignee → conflict detected
  - **Regression:** `pytest tests/k1/tools/family/tasks/ -v` — all existing task tests pass

---

## Epic 11: Reminders Connector — Full API Design

**Goal:** Upgrade reminders with full constitution, policy, guide cards, ontology, and JSON schemas. Follows the calendar pattern (Epic 9) with reminder-specific rules.

### Issue 11.1 — Reminders Constitution (YAML)

```yaml
constitution:
  connector_id: "family.reminders"
  constitution_id: "family.reminders.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]
  prerequisite_reads:
    - operation: "list"
      resource_kind: "reminder"
      reason: "Check for duplicate reminders at the same time for the same person."
      required: true
      timeout_ms: 5000
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["reminder"]
      description: "New reminder must not duplicate an existing reminder at the same time."
  companion_resource_roles:
    - resource_kind: "calendar_event"
      role: "dependency"
      description: "Reminder may reference a calendar event."
  hil_gates:
    - trigger: "missing_required_field"
      field: "time"
      prompt: "What time should the reminder fire?"
    - trigger: "missing_required_field"
      field: "person"
      prompt: "Who is this reminder for?"
    - trigger: "ambiguous_person"
      prompt: "Which person did you mean?"
  mutation_sequencing:
    - order: 1, phase: "read", operation: "list", description: "Read current reminders before mutating."
    - order: 2, phase: "mutate", operation: "create", description: "Create the reminder if no duplicate detected."
    - order: 3, phase: "read", operation: "list", description: "Verify reminder was created (read_after_write)."
  verification_requirements:
    - method: "read_after_write"
      required_for_submit: true
    - method: "output_schema"
  precondition_summary: "List reminders before creating to check for duplicates."
  companion_resource_summary: "Reminders may reference calendar events."
  hil_trigger_summary: "HIL required when reminder time or person is missing."
  degradation_policy: "If read_after_write verification fails, retry once then submit degraded."
```

### Issue 11.2 — Reminders Policy + Guide Cards + Ontology

- **Policy:** `write_requires_actor_role: []` (default-allow). Protected: `rem_*` patterns restricted to `["parent", "self"]`.
- **Guide cards:** Migrate `k1/contracts/prompts/reminders_activity_v1.yaml`. Include: specify clear time, remind for specific person, reference events in notes.
- **Ontology:** `concept_aliases`: "alert"→"reminder", "nag"→"reminder", "notify"→"reminder", "remind me"→"reminder". `resource_connector_edges`: `{resource_family: "reminder", connector_id: "family.reminders", role: "primary"}`, `{resource_family: "calendar_event", connector_id: "family.reminders", role: "companion"}`. `operation_equivalences`: `{canonical: "list", equivalent: "search"}`. `operation_aliases`: "remind"→create, "set"→create, "snooze"→update.
- **JSON Schemas:** Add `input_schema` + `output_schema` to all `ActionSpec` entries in `REMINDERS_DEFINITION`.

### Issue 11.3 — Reminders Tests

- **GAP-P1-025:** `tests/k1/fabric/connectors/test_family_reminders.py`
  - `TestConstitutionValidates` — reminders constitution passes validation
  - `TestResolveSituationReminderIntent` — "remind Riley to take medicine at 8pm" → `can_execute`
  - **Regression:** `pytest tests/k1/tools/family/reminders/ -v` — all existing tests pass

---

## Epic 12: Chores Connector — Full API Design

**Goal:** Upgrade chores with full constitution, policy, guide cards, ontology, and JSON schemas.

### Issue 12.1 — Chores Constitution (YAML)

```yaml
constitution:
  connector_id: "family.chores"
  constitution_id: "family.chores.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]
  prerequisite_reads:
    - operation: "list"
      resource_kind: "chore"
      reason: "Check for existing chore assignments before creating or reassigning."
      required: true
      timeout_ms: 5000
  conflict_analysis_rules:
    - check: "time_overlap"
      with_resource_kinds: ["calendar_event", "chore"]
      description: "New chore must not conflict with scheduled events or other chores."
  companion_resource_roles:
    - resource_kind: "calendar_event"
      role: "conflict_source"
      description: "Chores may conflict with calendar events in the same time window."
  hil_gates:
    - trigger: "missing_required_field"
      field: "title"
      prompt: "What chore needs to be done?"
    - trigger: "missing_required_field"
      field: "assignee"
      prompt: "Who should do this chore?"
    - trigger: "ambiguous_person"
      prompt: "Which person did you mean?"
  mutation_sequencing:
    - order: 1, phase: "read", operation: "list", description: "Read current chore list before mutating."
    - order: 2, phase: "mutate", operation: "create", description: "Create the chore if no conflicts detected."
    - order: 3, phase: "read", operation: "list", description: "Verify chore was created (read_after_write)."
  verification_requirements:
    - method: "read_after_write"
      required_for_submit: true
    - method: "output_schema"
  precondition_summary: "List chores before creating to check for conflicts with existing chores and calendar events."
  companion_resource_summary: "Chores conflict with calendar events in the same time window."
  hil_trigger_summary: "HIL required when chore title or assignee is missing."
  degradation_policy: "If read_after_write verification fails, retry once then submit degraded."
```

### Issue 12.2 — Chores Policy + Guide Cards + Ontology

- **Policy:** `write_requires_actor_role: ["parent", "guardian"]` — only parents/guardians can assign. Protected: `chore_points_*` restricted to `["parent", "self"]`. HIL trigger: child write → ask parent.
- **Guide cards:** Migrate `k1/contracts/prompts/chores_activity_v1.yaml`. Include: list before assign, check calendar availability, be specific, set due dates.
- **Ontology:** `concept_aliases`: "clean"→"chore", "housework"→"chore". `resource_connector_edges`: `{resource_family: "chore", connector_id: "family.chores", role: "primary"}`, `{resource_family: "calendar_event", connector_id: "family.chores", role: "companion"}`. `operation_equivalences`: `{canonical: "list", equivalent: "search"}`. `operation_aliases`: "assign"→create, "complete"→update, "finish"→update.
- **JSON Schemas:** Add `input_schema` + `output_schema` to all `ActionSpec` entries in `CHORES_DEFINITION`.

### Issue 12.3 — Chores Tests

- **GAP-P1-026:** `tests/k1/fabric/connectors/test_family_chores.py`
  - `TestConstitutionValidates` — chores constitution passes validation
  - `TestPolicyRestrictsChildAssignment` — child actor role → policy gates chore assignment
  - **Regression:** `pytest tests/k1/tools/family/chores/ -v` — all existing tests pass

---

## Epic 13: Shopping Connector — Full API Design

**Goal:** Upgrade shopping with full constitution, policy, guide cards, ontology, and JSON schemas.

### Issue 13.1 — Shopping Constitution (YAML)

```yaml
constitution:
  connector_id: "family.shopping"
  constitution_id: "family.shopping.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]
  prerequisite_reads:
    - operation: "list"
      resource_kind: "shopping_item"
      reason: "Check for duplicate items before adding to the list."
      required: true
      timeout_ms: 5000
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["shopping_item"]
      description: "New item must not duplicate an existing item on the active list."
  companion_resource_roles: []
  hil_gates:
    - trigger: "missing_required_field"
      field: "name"
      prompt: "What item should I add to the shopping list?"
    - trigger: "missing_required_field"
      field: "quantity"
      prompt: "How many do you need?"
  mutation_sequencing:
    - order: 1, phase: "read", operation: "list", description: "Read current shopping list before mutating."
    - order: 2, phase: "mutate", operation: "create", description: "Add item if no duplicate detected."
    - order: 3, phase: "read", operation: "list", description: "Verify item was added (read_after_write)."
  verification_requirements:
    - method: "read_after_write"
      required_for_submit: true
    - method: "output_schema"
  precondition_summary: "List shopping items before adding to check for duplicates."
  companion_resource_summary: null
  hil_trigger_summary: "HIL required when item name or quantity is missing."
  degradation_policy: "If read_after_write verification fails, retry once then submit degraded."
```

### Issue 13.2 — Shopping Policy + Guide Cards + Ontology

- **Policy:** `write_requires_actor_role: []` (default-allow — shopping lists are shared). No protected resources.
- **Guide cards:** Migrate `k1/contracts/prompts/shopping_activity_v1.yaml`. Include: list before add, group similar items, note quantities/preferences, mark purchased.
- **Ontology:** `concept_aliases`: "groceries"→"shopping_item", "buy"→"shopping_item", "shopping list"→"shopping_item". `resource_connector_edges`: `{resource_family: "shopping_item", connector_id: "family.shopping", role: "primary"}`. `operation_equivalences`: `{canonical: "list", equivalent: "search"}`. `operation_aliases`: "add"→create, "buy"→update, "purchased"→update.
- **JSON Schemas:** Add `input_schema` + `output_schema` to all `ActionSpec` entries in `SHOPPING_DEFINITION`.

### Issue 13.3 — Shopping Tests

- **GAP-P1-027:** `tests/k1/fabric/connectors/test_family_shopping.py`
  - `TestConstitutionValidates` — shopping constitution passes validation
  - `TestResolveSituationShoppingIntent` — "add milk to the shopping list" → `can_execute`
  - **Regression:** `pytest tests/k1/tools/family/shopping/ -v` — all existing tests pass

---

## Epic 14: Activity Profile Cleanup

**Goal:** After Epics 9-13 migrated all 5 activity profile YAMLs into connector guide cards, remove old `prompt_contract` files from discovery and clean up the dual-registration path.

**Design derivation from Epics 1-8:**

- Epics 9-13 populated `ToolDefinition.guide_cards` from the 5 YAML activity profiles
- `PromptPackBuilder` (Epic 6.3) reads guide cards from `GlobalProjectionStore`
- The old `ModuleLoader` → `PromptContract` → `CapabilityRegistry` path still loads these YAMLs and pollutes `discover_capabilities`
- `ContextBuilder` (existing, unchanged) needs `activity_profile` lookup — currently reads from `PromptContract` in `CapabilityRegistry`
- After migration, `ContextBuilder` reads from `ToolDefinition.activity_profile` (existing field on `ToolDefinition`)

### Issue 14.1 — Filter PromptContract from discover_capabilities

- **File:** `k1/fabric/retrieval/retrieval_engine.py`
- **Change:** In `discover_capabilities()`, filter out `isinstance(contract, PromptContract)`. Return only `CapabilityContract` + `AgentContract` + `WorkflowContract`.
- **Rationale:** Activity profiles are NOT executable capabilities. The LLM should discover capabilities through `resolve_situation` (which injects guide cards via `PromptPackBuilder` at the correct disclosure phase).
- **Note:** `find_relevant_prompts()` is UNCHANGED.

### Issue 14.2 — Extend ContextBuilder for ToolDefinition Activity Profiles

- **File:** `k1/fabric/context/builder.py` (or equivalent)
- **Change:** When resolving `activity_profile` references, check `ToolDefinition.activity_profile` first. Fall back to `CapabilityRegistry` for backward compatibility.
- **Precondition:** Deploy BEFORE deleting YAML files (Issue 14.3).

### Issue 14.3 — Remove Migrated YAML Files

- **Delete (5):** `calendar_activity_v1.yaml`, `tasks_activity_v1.yaml`, `reminders_activity_v1.yaml`, `chores_activity_v1.yaml`, `shopping_activity_v1.yaml`
- **Keep (3):** `system_of_record_generic_v1.yaml`, `mcp_generic_activity_v1.yaml`, `wasm_generic_activity_v1.yaml`

### Issue 14.4 — Verify Clean Discovery

- **GAP-P1-014:** `tests/k1/fabric/retrieval/test_activity_profile_filtering.py`
  - `test_discover_capabilities_excludes_prompt_contracts` — zero `PromptContract` entries for family domain
  - `test_find_relevant_prompts_still_works` — returns 3 generic profiles
  - `test_context_builder_reads_from_tool_definition` — resolves `calendar.v1` from `CalendarToolService.DEFINITION.activity_profile`
  - `TestAll5ConnectorsHaveGuideCards` — each has non-empty `guide_cards`
- **Run:** `pytest tests/k1/fabric/retrieval/test_activity_profile_filtering.py -v`

---

## System Coherence: Epics 9-14 in Context

**Two registration paths — one store, one truth:**

```
bootstrap_family_tools()  (kernel S8)
│
├─ ToolRegistry.register_class(CalendarToolService)
│    ├─ CapabilityRegistry.register(contract)         ← LEGACY PATH (unchanged)
│    └─ register_definition_to_store(DEFINITION, gps) ← NEW PATH (Epic 9.8-9.9)
│         └─ upsert connector + capabilities + constitution + ontology
│
├─ ToolRegistry.register_class(TasksToolService)      ← same pattern
├─ ToolRegistry.register_class(RemindersToolService)   ← same pattern
├─ ToolRegistry.register_class(ChoresToolService)      ← same pattern
└─ ToolRegistry.register_class(ShoppingToolService)    ← same pattern

Post-S8 (Epic 7.3):
  ManifestAdmissionService.admit_all(build_domain_corpus("family"))
    └─ Loads BASELINE ontology for family domain (10 connectors)
    └─ Family tool registrations (above) ENRICH the baseline
    └─ upsert semantics → family tool entries take precedence
```

**What each connector provides to the kernel:**

| Connector | Resource | Capabilities | Key Constitution Gates | Unique Policy Rule |
|-----------|----------|-------------|----------------------|-------------------|
| Calendar | `calendar_event`, `appointment` | create, list, update, delete | time_overlap, participant_availability, prerequisite list-before-create | Protected parent calendar |
| Tasks | `task` | create, list, update, delete | duplicate title+assignee | Default-allow |
| Reminders | `reminder` | create, list, update, delete | duplicate time+person, calendar_event dependency | Restricted read for other members |
| Chores | `chore` | create, list, update, delete | time_overlap with calendar, parent/guardian write-only | Child assignment gated |
| Shopping | `shopping_item` | create, list, update, delete | duplicate item name | Default-allow (shared list) |

**What the kernel provides back:**

- `ResolveSituationService` enforces every constitution rule (13-step cascade, Epic 6.2)
- `PolicySelectorService` gates on `list[ResolvedIntentType]` using the policy declarations above (Epic 4.1)
- `CapabilityBinderService` discovers companion resources via constitution (Epic 6.1)
- `PromptPackBuilder` injects guide cards into LLM context (Epic 6.3)
- `VerificationPlanRunner` verifies writes via `read_after_write` (Epic 4.2)

---

## Compatibility Summary (Revised)

| Component | Phase 1 Impact | Risk |
|-----------|---------------|------|
| `ToolDefinition` | Gains 6 optional fields — backward compatible | Low — all `Optional`, `default=None` |
| `ActionSpec` | Gains `input_schema` + `output_schema` optional fields | Low — falls back to `FieldSpec` |
| `ManifestTranslator` | Gains `register_definition_to_store()` — additive | Low — existing `register_definition()` unchanged |
| `CapabilityRegistry` | Unchanged | Zero |
| `NativeToolProvider._execute()` | Unchanged | Zero |
| `ToolRegistry.register_class()` | Adds one `if gps:` block | Low — gated behind store existence |
| `bootstrap_family_tools()` | Unchanged — new path is additive | Zero |
| `CapabilityFabric._execute_impl()` | Step 0 idempotency check via `_idempotency_store` | Low — gated behind store existence |
| `RetrievalEngine.discover_capabilities()` | Filters `PromptContract` — narrows results | Low — removes non-executable entries |
| `ContextBuilder` | Extended to read `ToolDefinition.activity_profile` | Low — fallback to registry preserved |
| **Calendar constitution** | Full typed artifact per `ConstitutionArtifact` | Med — first real constitution, validated by `CONSTITUTION_JSON_SCHEMA` |
| **Tasks/Reminders/Chores/Shopping constitutions** | Full typed artifacts following calendar pattern | Low — pattern proven by Calendar (Epic 9) |
| **Activity profiles** | 5 migrated to guide cards, 3 kept as generic | Low — `ContextBuilder` path preserved |
| **Domain catalog** | Family domain baseline ontology loaded at Post-S8 | Low — enriches but doesn't replace family tool entries |

**Key invariant:** Family tools continue to execute through `NativeToolProvider._execute()` → `ToolRegistry.get_service()` → `service.dispatch()`. The new constitution, policy, guide cards, ontology, and JSON schemas are ADDITIVE. The two registration paths (`CapabilityRegistry` for execution + `GlobalProjectionStore` for resolution) are complementary, not conflicting.

---

## Summary — Phase 1.1 (Epics 9–14): Family Tool Constitution Enrichment

| Epic | Issues | Files Created | Files Modified | Tests |
|------|--------|--------------|----------------|-------|
| 9 — Calendar | 10 | 0 | 2 (definition.py, calendar/definition.py) | GAP-001 (extends), existing calendar tests |
| 10 — Tasks | 3 | 1 (test) | 1 (tasks/definition.py) | GAP-024, existing task tests |
| 11 — Reminders | 3 | 1 (test) | 1 (reminders/definition.py) | GAP-025, existing reminder tests |
| 12 — Chores | 3 | 1 (test) | 1 (chores/definition.py) | GAP-026, existing chore tests |
| 13 — Shopping | 3 | 1 (test) | 1 (shopping/definition.py) | GAP-027, existing shopping tests |
| 14 — Cleanup | 4 | 1 (test) | 2 (retrieval_engine.py, context/builder.py) | GAP-014 |
| **Total** | **26** | **5 new test files** | **8 modified** | **35+ tests (5 new + existing tools)** |

**Phase 1 + Phase 1.1 combined: 65 issues, 32 new files, 11 modified, ~285 tests.**
