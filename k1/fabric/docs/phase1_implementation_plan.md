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
      snapshot_types: Optional[list[str]] = Field(
          default=None,
          description="Snapshot types this connector participates in. E.g. ['daily_snapshot','weekly_overview']. Empty/absent = no participation. Used by lookup() tool for dynamic snapshot assembly."
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
  - `snapshot_types: ["daily_snapshot", "weekly_overview"]` — appears in daily and weekly lookups
  - `constitution:` — full constitution (see below)
  - `policy_declarations:` — policy rules (see below)
  - `guide_cards:` — migrate from `k1/contracts/prompts/calendar_activity_v1.yaml`
  - `ontology:` — concept aliases + edges (see below)
  - Each `ActionSpec` gets `input_schema` + `output_schema` (full JSON Schema dicts)

### Issue 9.3 — Calendar Constitution

> **Design principle:** The constitution encodes procedural rules Back's LLM reads
> to act correctly. Visibility / sensitive-keyword redaction is a session-level
> kernel policy (the LLM IS the logged-in user — what data it sees is enforced
> before it ever reaches the LLM). Role gates live in `policy_declarations`;
> the constitution focuses on what to check, what to do when a check fires,
> and what other tools/resources coordinate with this connector.

- **What:** Write the `constitution` block.

  ```yaml
  constitution:
    connector_id: "family.calendar"
    constitution_id: "family.calendar.v1"
    schema_version: "1.0.0"
    execution_phases: ["read", "mutate"]

    # ── What MUST I check before acting? ──
    prerequisite_reads:
      - operation: "list"
        resource_kind: "calendar_event"
        reason: "Check for time-window conflicts with existing events before creating or updating."
        required: true
        timeout_ms: 5000
      - operation: "list"
        resource_kind: "chore"
        reason: "Assigned chores in the same time window may conflict — warn the user."
        required: false  # advisory only — Back warns, doesn't block
        timeout_ms: 3000
      - operation: "list"
        resource_kind: "task"
        reason: "Due tasks in the same time window may conflict — warn the user."
        required: false
        timeout_ms: 3000

    # ── What could go wrong, and WHAT DO I DO about it? ──
    conflict_analysis_rules:
      - check: "time_overlap"
        with_resource_kinds: ["calendar_event"]
        description: "Two events at overlapping times for the same attendees."
        resolution: "Present the conflict to the user with these options: create anyway, pick a different time, or cancel. Do NOT silently overwrite."
      - check: "time_overlap"
        with_resource_kinds: ["chore"]
        description: "An assigned chore is due during this event's time window."
        resolution: "Warn: '{child} has chore '{chore_title}' due at {due_time}'. Offer: create event anyway, reschedule the chore, or cancel this event."
      - check: "time_overlap"
        with_resource_kinds: ["task"]
        description: "A task is due during this event's time window."
        resolution: "Warn: '{assignee} has task '{task_title}' due'. Offer: create event anyway or cancel."
      - check: "participant_availability"
        description: "All attendees must be free in the target time window."
        resolution: "If any participant has a conflicting event, list the conflict and ask whether to proceed."

    # ── What other tools/resources should I coordinate with? ──
    companion_resource_roles:
      - resource_kind: "chore"
        role: "conflict_source"
        description: "Calendar events may conflict with assigned chores in the same time window. When the user says 'assign kitchen cleanup to Riley weekly', that is a CHORE, not a calendar event — use family.chores."
      - resource_kind: "task"
        role: "conflict_source"
        description: "Calendar events may conflict with due tasks."
      - resource_kind: "reminder"
        role: "dependency"
        description: "Events can trigger reminders via event_offset triggers."
      - resource_kind: "shopping_item"
        role: "suggestion_source"
        description: "Events like 'birthday party Saturday' may suggest shopping items ('order cake?')."

    # ── When do I STOP and ask the human? ──
    hil_gates:
      - trigger: "missing_required_field"
        field: "title"
        prompt: "What should this event be called?"
      - trigger: "missing_required_field"
        field: "start"
        prompt: "What time does this event start?"
      - trigger: "missing_required_field"
        field: "end"
        prompt: "What time does this event end? (I'll default to 1 hour if not sure.)"
      - trigger: "missing_required_field"
        field: "resource_id"
        prompt: "Which calendar should I add this to?"
      - trigger: "time_conflict_detected"
        prompt: "This time conflicts with: {conflict_summary}. What should I do?"
        options: ["Create anyway", "Pick a different time", "Cancel"]
      - trigger: "ambiguous_person"
        prompt: "Which person did you mean? I found: {candidate_names}."
      - trigger: "child_creates_event"
        prompt: "{child_name} is creating an event. Notify parents?"
        options: ["Yes, notify parents", "Just create it"]

    # ── What order do I execute? ──
    mutation_sequencing:
      - order: 1
        phase: "read"
        operation: "list"
        description: "Read current calendar + chores + tasks for the target time window."
      - order: 2
        phase: "mutate"
        operation: "create"
        description: "Create the event if no blocking conflicts. If a soft conflict exists, present it to the user per conflict_analysis_rules resolution guidance above."
      - order: 3
        phase: "read"
        operation: "list"
        description: "Verify event was created (read_after_write)."

    # ── How do I prove it worked? ──
    verification_requirements:
      - method: "read_after_write"
        description: "Read back the created event and confirm all fields match."
        required_for_submit: true
      - method: "output_schema"
        description: "Validate the returned event matches the expected schema."

    # ── Summaries (injected into Back's prompt) ──
    precondition_summary: >
      Before creating or updating an event, I MUST list the calendar for the
      target time window. I SHOULD also check chores and tasks for soft conflicts.
      I present all conflicts to the user — I never silently overwrite.
    companion_resource_summary: >
      Calendar events conflict with chores and tasks in the same time window.
      Events can trigger reminders. Recurring events like birthdays can suggest
      shopping items. If the user describes something recurring with reward
      tracking, that is a CHORE (family.chores), not a calendar event.
    hil_trigger_summary: >
      I need human input when: title/start/end/calendar are missing, a time
      conflict is detected, a person reference is ambiguous, or a child is
      creating an event that should notify parents.
    degradation_policy: >
      If read_after_write verification fails, retry once. If still failing,
      submit degraded with the created event_id but flag verification=failed.
  ```

### Issue 9.4 — Calendar Policy Declarations

> **Design principle:** Policy declarations are enforced by
> `PolicySelectorService` — they gate what the LLM is ALLOWED to do based
> on actor role and safety band. The LLM does not read these; the resolver
> enforces them and reports violations via `machine_verdict`. Visibility
> (who can see what data) is a session-level kernel concern, not a
> connector policy — it's applied BEFORE data reaches the LLM.

- **What:** Write `policy_declarations`:

  ```yaml
  policy_declarations:
    # ── Per-operation role gates ──
    # create_event: any household role can create
    # update_event: parent/guardian only (kids can't edit after creation)
    # delete_event: parent/guardian only
    # set_visibility: parent only
    # connect_feed: parent only
    # list_feeds: parent/guardian only
    # respond_to_invite: any role
    operation_role_gates:
      create_event: ["parent", "child", "guardian"]
      update_event: ["parent", "guardian"]
      delete_event: ["parent", "guardian"]
      set_visibility: ["parent"]
      connect_feed: ["parent"]
      disconnect_feed: ["parent"]
      list_feeds: ["parent", "guardian"]
      respond_to_invite: ["parent", "child", "guardian"]

    # ── Safety band minimums per operation ──
    operation_safety_bands:
      create_event: "GREEN"
      update_event: "GREEN"
      delete_event: "AMBER"
      set_visibility: "AMBER"
      connect_feed: "AMBER"
      disconnect_feed: "AMBER"

    # ── Protected resource patterns (reads require specified role) ──
    protected_resources:
      - resource_id_pattern: "cal_parent_*"
        reason: "Parent calendar may contain sensitive appointments."
        required_role: "parent"

    # ── HIL triggers (policy-level, enforced by PolicySelectorService) ──
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

### Issue 10.1 — Tasks Constitution

> **Design principle:** Tasks are one-shot to-do items. Chores are recurring
>
> - gamified with reward ledgers. Back's LLM needs to know the difference
> so when the user says "assign kitchen cleanup to Riley every Tuesday"
> (which sounds like a task), Back recognizes it as a CHORE and crosses over
> to `family.chores`. This distinction lives in `companion_resource_roles`
> (so the resolver discovers the chore connector as a companion) AND in
> guide cards (so Back's prompt teaches the LLM the distinction).

```yaml
constitution:
  connector_id: "family.tasks"
  constitution_id: "family.tasks.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]

  # ── What MUST I check before acting? ──
  prerequisite_reads:
    - operation: "list"
      resource_kind: "task"
      reason: "Check for duplicate tasks (same title + same assignee) before creating."
      required: true
      timeout_ms: 5000
    - operation: "list"
      resource_kind: "calendar_event"
      reason: "Check for scheduling conflicts — a task due Friday may conflict with an event."
      required: false  # advisory — Back warns, doesn't block
      timeout_ms: 3000

  # ── What could go wrong, and WHAT DO I DO about it? ──
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["task"]
      description: "New task title must not match an existing open task for the same assignee."
      resolution: "Tell the user: '{assignee} already has an open task '{existing_title}'. Create anyway or update the existing task?"
    - check: "due_date_vs_calendar"
      with_resource_kinds: ["calendar_event"]
      description: "A task due at a specific time may conflict with a calendar event."
      resolution: "Warn the user if the task's due window overlaps a calendar event for the same assignee. Do not block — tasks are flexible."

  # ── What other tools/resources should I coordinate with? ──
  companion_resource_roles:
    - resource_kind: "calendar_event"
      role: "dependency"
      description: "Calendar events can auto-create tasks ('Riley has soccer at 5pm — create pack cleats task due 4:30pm')."
    - resource_kind: "chore"
      role: "distinct_sibling"
      description: >
        CRITICAL DISTINCTION: Tasks are ONE-SHOT ('pick up Riley today').
        Chores are RECURRING + GAMIFIED ('vacuum living room every Saturday,
        earn $2'). If the user describes something recurring with rewards,
        points, or allowance — that is a CHORE, not a task. Use
        family.chores, not family.tasks. If the user says 'assign kitchen
        cleanup to Riley weekly', that is a chore. If the user says 'remind
        Riley to do homework tonight', that is a task.

  # ── When do I STOP and ask the human? ──
  hil_gates:
    - trigger: "missing_required_field"
      field: "title"
      prompt: "What should the task be called?"
    - trigger: "missing_required_field"
      field: "assignee"
      prompt: "Who should this task be assigned to?"
    - trigger: "ambiguous_person"
      prompt: "Which person did you mean? I found: {candidate_names}."
    - trigger: "duplicate_detected"
      prompt: "{assignee} already has '{existing_title}'. Create anyway or update the existing one?"
      options: ["Create anyway", "Update existing", "Cancel"]

  # ── What order do I execute? ──
  mutation_sequencing:
    - order: 1
      phase: "read"
      operation: "list"
      description: "Read current task list + calendar for the assignee."
    - order: 2
      phase: "mutate"
      operation: "create"
      description: "Create the task if no duplicate detected. Warn about calendar conflicts if any."
    - order: 3
      phase: "read"
      operation: "list"
      description: "Verify task was created (read_after_write)."

  # ── How do I prove it worked? ──
  verification_requirements:
    - method: "read_after_write"
      description: "Read back the created task and confirm all fields match."
      required_for_submit: true
    - method: "output_schema"
      description: "Validate the returned task matches the expected schema."

  # ── Summaries (injected into Back's prompt) ──
  precondition_summary: >
    Before creating a task, I MUST list existing tasks to check for duplicates
    (same title + same assignee). I SHOULD check the assignee's calendar for
    scheduling awareness. Tasks are flexible — I warn about conflicts but
    don't block.
  companion_resource_summary: >
    Tasks can be auto-created from calendar events. Tasks are DISTINCT from
    chores: tasks are one-shot, chores are recurring with reward tracking.
    See the 'Tasks vs Chores' guide card for the full distinction rules.
  hil_trigger_summary: >
    I need human input when: task title or assignee is missing, the person
    reference is ambiguous, or a duplicate task is detected.
  degradation_policy: >
    If read_after_write verification fails, retry once then submit degraded.
```

### Issue 10.2 — Tasks Policy + Guide Cards + Ontology

- **Manifest:** `snapshot_types: ["daily_snapshot", "weekly_overview"]` — tasks appear in daily and weekly lookups.

- **Policy:** Per-operation role gates — `create_task`: any role, `reassign_task`: parent/guardian only, `complete_task`: any role. Safety bands: `create_task`: GREEN, `reassign_task`: AMBER. No protected resources.

  ```yaml
  policy_declarations:
    operation_role_gates:
      create_task: ["parent", "child", "guardian"]
      update_task: ["parent", "guardian"]
      complete_task: ["parent", "child", "guardian"]
      delete_task: ["parent", "guardian"]
      reassign_task: ["parent", "guardian"]
    operation_safety_bands:
      create_task: "GREEN"
      reassign_task: "AMBER"
      delete_task: "AMBER"
  ```

- **Guide cards:** The Tasks-vs-Chores distinction is the critical card. Also: list before create, assign explicitly, use priority/urgency hints, auto-create from calendar events.

  ```yaml
  guide_cards:
    - guide_id: "family.tasks.guide.01"
      title: "Tasks vs Chores — Know the Difference"
      content: |
        TASKS are ONE-SHOT to-do items:
          "Pick up Riley from school today"
          "Remind Riley to do homework tonight"
          "Buy birthday cake for Saturday's party"
        Tasks have NO rewards, NO recurrence, NO parent verification gate.
        When done, just mark complete_task().

        CHORES are RECURRING + GAMIFIED:
          "Vacuum living room every Saturday — earn $2"
          "Clean kitchen nightly — earn $1.50"
          "Mow the lawn weekly — earn $5"
        Chores have rewards, allowance tracking, parent verify_chore() gate,
        and redemption via redeem_reward().

        RED FLAGS that mean CHORE not task:
        - "every [day/week/Saturday]" → recurring = chore
        - "earn [$amount]" or "points" or "allowance" → reward = chore
        - "assign [child] to [recurring duty]" → chore
        - Parent needs to "verify" or "approve" → chore

        If ANY red flag is present, use family.chores tools, not family.tasks.
      relevance: "always"
      disclosure_phase: "connector_summary"

    - guide_id: "family.tasks.guide.02"
      title: "Creating Tasks from Calendar Events"
      content: |
        Calendar events often imply tasks:
        - "Riley has soccer at 5pm" → create "pack cleats" task due 4:30pm
        - "Family dinner Saturday" → create "buy groceries" task due Friday
        - "Doctor appointment Tuesday" → create "fill prescription" task

        When you see a calendar event, check if it implies a task and
        suggest it to the user. Do NOT auto-create without asking.
      relevance: "on_conflict"
      disclosure_phase: "tool_name_selection"
  ```

- **Ontology:** `concept_aliases`: "todo"→"task", "homework"→"task", "errand"→"task", "remind me to"→"task". `resource_connector_edges`: `{resource_family: "task", connector_id: "family.tasks", role: "primary"}`, `{resource_family: "calendar_event", connector_id: "family.tasks", role: "companion"}`, `{resource_family: "chore", connector_id: "family.tasks", role: "companion"}`. `operation_aliases`: "assign"→create, "complete"→complete_task, "finish"→complete_task, "add"→create.

### Issue 10.3 — Tasks Tests

- **GAP-P1-024:** `tests/k1/fabric/connectors/test_family_tasks.py`
  - `TestConstitutionValidates` — tasks constitution passes `validate_constitution()`
  - `TestResolveSituationTaskIntent` — "add homework for Riley due Friday" → `can_execute` with `tool.execute.family.tasks.create` as primary
  - `TestDuplicateTaskBlocked` — same title + assignee → conflict detected
  - **Regression:** `pytest tests/k1/tools/family/tasks/ -v` — all existing task tests pass

---

## Epic 11: Reminders Connector — Full API Design

**Goal:** Upgrade reminders with full constitution, policy, guide cards, ontology, and JSON schemas. Follows the calendar pattern (Epic 9) with reminder-specific rules.

### Issue 11.1 — Reminders Constitution

> **Design principle:** Reminders are pure notifications — they fire at a time,
> they notify, they're done. They are NOT tracked action items (that's a task)
> and NOT recurring gamified duties (that's a chore). Reminders do NOT check
> for calendar conflicts — a reminder at 3pm ("take pill") and a soccer
> event at 3pm are orthogonal. The only cross-app concern is: if the reminder
> references a calendar event ("30 minutes before Riley's soccer"), verify the
> event still exists so the reminder doesn't fire on a deleted event.

```yaml
constitution:
  connector_id: "family.reminders"
  constitution_id: "family.reminders.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]

  # ── What MUST I check before acting? ──
  prerequisite_reads:
    - operation: "list"
      resource_kind: "reminder"
      reason: "Check for duplicate reminders (same person + same time + same message) before creating."
      required: true
      timeout_ms: 5000
    - operation: "list"
      resource_kind: "calendar_event"
      reason: "If the reminder has an event_ref, verify the referenced calendar event still exists. If deleted, the reminder would fire at a computed time based on nothing — warn the user."
      required: false  # advisory — only when event_ref is set
      timeout_ms: 3000

  # ── What could go wrong, and WHAT DO I DO about it? ──
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["reminder"]
      description: "New reminder must not duplicate an existing reminder for the same person at the same time with the same message."
      resolution: "Tell the user: '{person} already has a reminder '{existing_message}' at {time}'. Offer: create anyway or cancel."
    - check: "invalid_event_ref"
      with_resource_kinds: ["calendar_event"]
      description: "The referenced calendar event no longer exists (deleted or moved)."
      resolution: "Warn: 'The event '{event_title}' was deleted. The reminder will still fire at {computed_time} but won't reference a valid event.' Offer: create anyway, pick a different event, or cancel."

  # ── What other tools/resources should I coordinate with? ──
  companion_resource_roles:
    - resource_kind: "calendar_event"
      role: "dependency"
      description: "Reminders can fire at event offsets ('30 minutes before Riley's soccer'). The reminder depends on the event existing — if the event is deleted, warn the user per conflict_analysis_rules above."
    - resource_kind: "task"
      role: "distinct_sibling"
      description: >
        CRITICAL DISTINCTION: Reminders are PURE NOTIFICATIONS ('remind Riley
        to take medicine at 8pm'). Tasks are ONE-SHOT action items ('pick up
        Riley today'). If the user says 'remind me to X', that's a reminder.
        If the user says 'I need to X' or 'add X to my list', that's a task.
        See the 'Reminders vs Tasks' guide card for the full distinction rules.

  # ── When do I STOP and ask the human? ──
  hil_gates:
    - trigger: "missing_required_field"
      field: "time"
      prompt: "What time should the reminder fire?"
    - trigger: "missing_required_field"
      field: "person"
      prompt: "Who is this reminder for?"
    - trigger: "missing_required_field"
      field: "message"
      prompt: "What should the reminder say?"
    - trigger: "ambiguous_person"
      prompt: "Which person did you mean? I found: {candidate_names}."

  # ── What order do I execute? ──
  mutation_sequencing:
    - order: 1
      phase: "read"
      operation: "list"
      description: "Read current reminders + calendar event if event_ref is set."
    - order: 2
      phase: "mutate"
      operation: "create"
      description: "Create the reminder if no duplicate detected. Warn about invalid event_ref if applicable."
    - order: 3
      phase: "read"
      operation: "list"
      description: "Verify reminder was created (read_after_write)."

  # ── How do I prove it worked? ──
  verification_requirements:
    - method: "read_after_write"
      description: "Read back the created reminder and confirm all fields match."
      required_for_submit: true
    - method: "output_schema"
      description: "Validate the returned reminder matches the expected schema."

  # ── Summaries (injected into Back's prompt) ──
  precondition_summary: >
    Before creating a reminder, I MUST list existing reminders for the same
    person to check for duplicates. If the reminder references a calendar
    event (event_ref), I SHOULD verify the event still exists. Reminders are
    pure notifications — I do NOT check for calendar scheduling conflicts.
  companion_resource_summary: >
    Reminders can fire at calendar event offsets. Reminders are DISTINCT from
    tasks: reminders are pure notifications ('remind me to X at Y time'),
    tasks are action items ('I need to do X'). See the 'Reminders vs Tasks'
    guide card for the full distinction rules.
  hil_trigger_summary: >
    I need human input when: reminder time, person, or message is missing, or
    a person reference is ambiguous.
  degradation_policy: >
    If read_after_write verification fails, retry once then submit degraded.
```

### Issue 11.2 — Reminders Policy + Guide Cards + Ontology

- **Manifest:** `snapshot_types: ["daily_snapshot", "weekly_overview"]` — reminders appear in daily and weekly lookups.

- **Policy:** Per-operation role gates — `create_reminder`: any role (anyone can set reminders), `delete_reminder`: self or parent (you can delete your own; parents can delete kids'), `update_reminder`: self or parent. All operations GREEN safety band — reminders are low-risk. No protected resources.

  ```yaml
  policy_declarations:
    operation_role_gates:
      create_reminder: ["parent", "child", "guardian"]
      update_reminder: ["parent", "child", "guardian"]
      delete_reminder: ["parent", "child", "guardian"]
    operation_safety_bands:
      create_reminder: "GREEN"
      update_reminder: "GREEN"
      delete_reminder: "GREEN"
  ```

- **Guide cards:** The Reminders-vs-Tasks distinction is the critical card. Also: specify clear time + message, reference calendar events with offset syntax, reminders are cheap — don't over-gate with HIL.

  ```yaml
  guide_cards:
    - guide_id: "family.reminders.guide.01"
      title: "Reminders vs Tasks — Know the Difference"
      content: |
        REMINDERS are PURE NOTIFICATIONS:
          "Remind Riley to take medicine at 8pm"
          "Remind me to call the dentist tomorrow at 9am"
          "Remind Riley 30 minutes before soccer practice"
        Reminders fire once, notify, and are done. No tracking, no completion
        state, no rewards. They are cheap — create freely.

        TASKS are ONE-SHOT ACTION ITEMS:
          "Pick up Riley from school today"
          "Buy birthday cake for Saturday's party"
          "I need to finish the report by Friday"
        Tasks are tracked, have completion state, and may have due dates.

        RED FLAGS that mean TASK not reminder:
        - "I need to [do X]" → task
        - "add [X] to my list" → task
        - "[X] is due [date]" → task
        - "don't forget to [X]" → could be either — ask if they want a reminder or a task

        If ANY red flag is present, consider family.tasks instead of family.reminders.
      relevance: "always"
      disclosure_phase: "connector_summary"

    - guide_id: "family.reminders.guide.02"
      title: "Creating Reminders from Calendar Events"
      content: |
        Reminders can fire at offsets from calendar events:
        - "Remind Riley 30 minutes before soccer practice"
        - "Remind me 1 hour before the dentist appointment"
        - "Remind everyone at event start for family dinner"

        Offset syntax: "{N} minutes/hours before/after {event}".
        Always verify the event still exists before creating the reminder.
        If the event is deleted, warn the user but still allow reminder creation.
      relevance: "on_conflict"
      disclosure_phase: "tool_name_selection"
  ```

- **Ontology:** `concept_aliases`: "alert"→"reminder", "nag"→"reminder", "notify"→"reminder", "remind me"→"reminder", "ping"→"reminder". `resource_connector_edges`: `{resource_family: "reminder", connector_id: "family.reminders", role: "primary"}`, `{resource_family: "calendar_event", connector_id: "family.reminders", role: "companion"}`, `{resource_family: "task", connector_id: "family.reminders", role: "companion"}`. `operation_aliases`: "remind"→create, "set"→create, "snooze"→update, "notify"→create.

### Issue 11.3 — Reminders Tests

- **GAP-P1-025:** `tests/k1/fabric/connectors/test_family_reminders.py`
  - `TestConstitutionValidates` — reminders constitution passes validation
  - `TestResolveSituationReminderIntent` — "remind Riley to take medicine at 8pm" → `can_execute`
  - **Regression:** `pytest tests/k1/tools/family/reminders/ -v` — all existing tests pass

---

## Epic 12: Chores Connector — Full API Design

**Goal:** Upgrade chores with full constitution, policy, guide cards, ontology, and JSON schemas.

### Issue 12.1 — Chores Constitution

> **Design principle:** Chores are recurring + gamified with reward ledgers.
> Back's LLM needs to know the chore lifecycle: `create_chore()` (parent assigns)
> → `complete_chore()` (child marks done) → `verify_chore()` (parent confirms)
> → reward credits → `redeem_reward()` (child spends earnings). This is the
> core gamification loop. Calendar events take precedence over recurring chore
> slots because events are specific one-time commitments; chores are flexible
> recurring duties. Workload balance is checked procedurally (count chores per
> person) but the resolution is always advisory — the parent decides.

```yaml
constitution:
  connector_id: "family.chores"
  constitution_id: "family.chores.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]

  # ── What MUST I check before acting? ──
  prerequisite_reads:
    - operation: "list"
      resource_kind: "chore"
      reason: "Check for duplicate chore assignments (same assignee + same title + same recurrence pattern) before creating."
      required: true
      timeout_ms: 5000
    - operation: "list"
      resource_kind: "calendar_event"
      reason: "Check the assignee's calendar for the chore's recurring time window. A 'Saturdays 10am' chore may conflict with a specific Saturday event."
      required: false  # advisory — calendar events take precedence, but chores are flexible
      timeout_ms: 3000

  # ── What could go wrong, and WHAT DO I DO about it? ──
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["chore"]
      description: "New chore must not duplicate an existing chore for the same assignee with the same title and recurrence pattern."
      resolution: "Tell the user: '{assignee} already has chore '{existing_title}' with the same schedule. Create anyway or update the existing chore?"
    - check: "time_overlap"
      with_resource_kinds: ["calendar_event"]
      description: "The chore's recurring time slot conflicts with a specific calendar event. Calendar events take precedence because they are specific one-time commitments; chores are recurring and flexible."
      resolution: "Warn: '{assignee} has '{event_title}' during the chore's regular time on {dates}. The child can work around the event — do not block. Offer: keep chore as-is (child works around event), adjust time for those specific dates, or cancel."
    - check: "workload_balance"
      with_resource_kinds: ["chore"]
      description: "One household member has significantly more chores than others. This is a fairness check — advisory only, never blocking."
      resolution: "If one person has ≥3 more chores than another, mention it: '{person} has {n} chores/week, {other} has {m}. Would you like to balance the workload?' The parent always decides — do NOT block chore creation for workload balance."

  # ── What other tools/resources should I coordinate with? ──
  companion_resource_roles:
    - resource_kind: "calendar_event"
      role: "conflict_source"
      description: "Calendar events take precedence over recurring chore slots. Chores are flexible — the child works around specific events."
    - resource_kind: "task"
      role: "distinct_sibling"
      description: >
        CRITICAL DISTINCTION: Chores are RECURRING + GAMIFIED ('vacuum every
        Saturday, earn $2'). Tasks are ONE-SHOT ('pick up Riley today'). If
        the user describes something recurring with rewards, points, or
        allowance — that is a CHORE. If the user says 'assign kitchen cleanup
        to Riley weekly', that is a chore. If the user says 'remind Riley to
        do homework tonight', that is a task (family.tasks) or a reminder
        (family.reminders). See the 'Chores vs Tasks' guide card.

  # ── When do I STOP and ask the human? ──
  hil_gates:
    - trigger: "missing_required_field"
      field: "title"
      prompt: "What chore needs to be done?"
    - trigger: "missing_required_field"
      field: "assignee"
      prompt: "Who should do this chore?"
    - trigger: "missing_required_field"
      field: "frequency"
      prompt: "How often should this chore be done? (daily, weekly, every Saturday, etc.)"
    - trigger: "ambiguous_person"
      prompt: "Which person did you mean? I found: {candidate_names}."
    - trigger: "time_conflict_detected"
      prompt: "This chore's time conflicts with: {conflict_summary}. What should I do?"
      options: ["Keep chore as-is (child works around event)", "Adjust time for conflicting dates", "Cancel"]
    - trigger: "child_marks_complete"
      prompt: "{child_name} marked '{chore_title}' as done. Verify completion?"
      options: ["Yes, verify — credit reward", "Not yet — remind them what's needed", "Reject — chore not done properly"]

  # ── What order do I execute? ──
  mutation_sequencing:
    - order: 1
      phase: "read"
      operation: "list"
      description: "Read current chore list + calendar for the assignee's recurring time window."
    - order: 2
      phase: "mutate"
      operation: "create"
      description: "Create the chore if no duplicate detected. Warn about calendar conflicts (advisory). Check workload balance (advisory)."
    - order: 3
      phase: "read"
      operation: "list"
      description: "Verify chore was created (read_after_write)."

  # ── How do I prove it worked? ──
  verification_requirements:
    - method: "read_after_write"
      description: "Read back the created chore and confirm all fields match."
      required_for_submit: true
    - method: "output_schema"
      description: "Validate the returned chore matches the expected schema."

  # ── Summaries (injected into Back's prompt) ──
  precondition_summary: >
    Before creating a chore, I MUST list existing chores to check for duplicates
    (same assignee + same title + same recurrence). I SHOULD check the assignee's
    calendar for time-window conflicts. Calendar events take precedence over
    recurring chore slots — chores are flexible. I SHOULD also check workload
    balance across household members (advisory only).
  companion_resource_summary: >
    Calendar events take precedence over recurring chore slots. Chores are
    DISTINCT from tasks: chores are recurring + gamified with reward ledgers,
    tasks are one-shot action items. Chores follow a lifecycle:
    create → complete (child) → verify (parent) → reward credits → redeem.
    See the 'Chores vs Tasks' and 'How Gamification Works' guide cards.
  hil_trigger_summary: >
    I need human input when: chore title, assignee, or frequency is missing,
    a person reference is ambiguous, a calendar time conflict is detected,
    or a child marks a chore as complete (parent verification is the core
    gamification mechanic).
  degradation_policy: >
    If read_after_write verification fails, retry once then submit degraded.
```

### Issue 12.2 — Chores Policy + Guide Cards + Ontology

- **Manifest:** `snapshot_types: ["daily_snapshot", "weekly_overview"]` — chores appear in daily and weekly lookups.

- **Policy:** Per-operation role gates reflect the chore lifecycle: `create_chore`: parent/guardian only (parents assign), `complete_chore`: any role (kids mark done, but goes to parent verification), `verify_chore`: parent/guardian only (the gamification gate), `redeem_reward`: any role with AMBER safety band (kids CAN redeem their own money, but parents may want visibility).

  ```yaml
  policy_declarations:
    operation_role_gates:
      create_chore: ["parent", "guardian"]
      update_chore: ["parent", "guardian"]
      delete_chore: ["parent", "guardian"]
      complete_chore: ["parent", "child", "guardian"]
      verify_chore: ["parent", "guardian"]
      redeem_reward: ["parent", "child", "guardian"]
    operation_safety_bands:
      create_chore: "GREEN"
      verify_chore: "GREEN"
      redeem_reward: "AMBER"
      delete_chore: "AMBER"
    protected_resources:
      - resource_id_pattern: "chore_ledger_*"
        reason: "Reward ledger contains allowance and earnings data."
        required_role: "parent"
    hil_triggers:
      - condition: "redeem_reward AND actor_role == 'child' AND amount > 10"
        prompt: "{child_name} wants to redeem ${amount}. Approve?"
  ```

- **Guide cards:** Three critical cards: Chores-vs-Tasks distinction, the gamification lifecycle, and fair workload distribution.

  ```yaml
  guide_cards:
    - guide_id: "family.chores.guide.01"
      title: "Chores vs Tasks — Know the Difference"
      content: |
        CHORES are RECURRING + GAMIFIED:
          "Vacuum living room every Saturday — earn $2"
          "Clean kitchen nightly — earn $1.50"
          "Mow the lawn weekly — earn $5"
        Chores have: recurrence schedule, reward amount, parent verify_chore()
        gate, allowance tracking, and redemption via redeem_reward().

        TASKS are ONE-SHOT to-do items:
          "Pick up Riley from school today"
          "Buy birthday cake for Saturday's party"
        Tasks have NO rewards, NO recurrence, NO parent verification gate.

        RED FLAGS that mean CHORE not task:
        - "every [day/week/Saturday]" → recurring = chore
        - "earn [$amount]" or "points" or "allowance" → reward = chore
        - "assign [child] to [recurring duty]" → chore
        - Parent needs to "verify" or "approve" → chore
        - "weekly", "daily", "monthly" → recurring = chore

        If ANY red flag is present, use family.chores, not family.tasks.
      relevance: "always"
      disclosure_phase: "connector_summary"

    - guide_id: "family.chores.guide.02"
      title: "How Chore Gamification Works"
      content: |
        The chore lifecycle has 4 stages:

        1. CREATE — Parent assigns chore with title, assignee, frequency,
           and reward amount. Example: "Riley vacuums living room every
           Saturday, earns $2."

        2. COMPLETE — Child marks the chore as done. This is NOT final —
           it enters a pending verification state. The child sees their
           chore marked complete but reward is not yet credited.

        3. VERIFY — Parent confirms the chore was done properly. This is
           the gamification gate. Only after verification are rewards
           credited to the child's ledger. The constitution HIL gate
           'child_marks_complete' fires here — always ask the parent.

        4. REDEEM — Child (or parent) redeems accumulated rewards.
           Policy: any role can redeem, but amounts over $10 trigger
           parent approval when initiated by a child.

        NEVER skip verification. The parent gate is what makes chores a
        trust-building tool, not just a todo list.
      relevance: "always"
      disclosure_phase: "connector_summary"

    - guide_id: "family.chores.guide.03"
      title: "Fair Workload Distribution"
      content: |
        When assigning chores, check the balance across household members:
        - Count chores per person (active, not completed).
        - If one person has ≥3 more chores than another, mention it.
        - Example: "Riley has 5 chores/week, Jordan has 1. Want to balance?"
        - This is ADVISORY ONLY — the parent always decides.
        - Do NOT block chore creation for workload balance.
        - Consider age-appropriateness: younger kids get fewer/simpler chores.
      relevance: "on_conflict"
      disclosure_phase: "tool_name_selection"
  ```

- **Ontology:** `concept_aliases`: "clean"→"chore", "housework"→"chore", "duty"→"chore", "responsibility"→"chore", "allowance"→"chore". `resource_connector_edges`: `{resource_family: "chore", connector_id: "family.chores", role: "primary"}`, `{resource_family: "calendar_event", connector_id: "family.chores", role: "companion"}`, `{resource_family: "task", connector_id: "family.chores", role: "companion"}`. `operation_aliases`: "assign"→create_chore, "complete"→complete_chore, "finish"→complete_chore, "verify"→verify_chore, "approve"→verify_chore, "redeem"→redeem_reward, "cash out"→redeem_reward.

### Issue 12.3 — Chores Tests

- **GAP-P1-026:** `tests/k1/fabric/connectors/test_family_chores.py`
  - `TestConstitutionValidates` — chores constitution passes validation
  - `TestPolicyRestrictsChildAssignment` — child actor role → policy gates chore assignment
  - **Regression:** `pytest tests/k1/tools/family/chores/ -v` — all existing tests pass

---

## Epic 13: Shopping Connector — Full API Design

**Goal:** Upgrade shopping with full constitution, policy, guide cards, ontology, and JSON schemas.

### Issue 13.1 — Shopping Constitution

> **Design principle:** Shopping is the simplest family connector — a shared list
> with no cross-app coordination requirements. It's a leaf node in the connector
> graph: other connectors may suggest shopping items (calendar events suggest
> "order cake"), but shopping doesn't need to read back from them. The only
> procedural rule is: list before add to avoid duplicates. Everything else is
> guide card material (best practices for list management).

```yaml
constitution:
  connector_id: "family.shopping"
  constitution_id: "family.shopping.v1"
  schema_version: "1.0.0"
  execution_phases: ["read", "mutate"]

  # ── What MUST I check before acting? ──
  prerequisite_reads:
    - operation: "list"
      resource_kind: "shopping_item"
      reason: "Check for duplicate items (same name, active list) before adding. The user may have already added 'milk' — adding it again creates confusion."
      required: true
      timeout_ms: 5000

  # ── What could go wrong, and WHAT DO I DO about it? ──
  conflict_analysis_rules:
    - check: "duplicate"
      with_resource_kinds: ["shopping_item"]
      description: "New item name matches an existing active item on the shopping list."
      resolution: "Tell the user: '{item_name}' is already on the list (added {when}, quantity: {qty}). Options: add anyway (separate entry), update quantity of existing item, or skip. Do NOT silently create a duplicate."

  # ── What other tools/resources should I coordinate with? ──
  companion_resource_roles:
    []
    # Shopping is a LEAF NODE in the connector graph. Other connectors may
    # suggest shopping items (calendar.birthday → 'order cake?', chore.supplies
    # → 'buy cleaning spray?'), but those suggestions flow FROM other connectors
    # TO shopping — not the reverse. Shopping does not need to read calendar,
    # tasks, chores, or reminders to function correctly. The empty companion
    # list is intentional and correct.

  # ── When do I STOP and ask the human? ──
  hil_gates:
    - trigger: "missing_required_field"
      field: "name"
      prompt: "What item should I add to the shopping list?"
    - trigger: "missing_required_field"
      field: "quantity"
      prompt: "How many do you need? (I'll default to 1 if not sure.)"
    - trigger: "duplicate_detected"
      prompt: "'{item_name}' is already on the list (qty: {existing_qty}). What should I do?"
      options: ["Add anyway (separate entry)", "Update quantity to {new_qty}", "Skip"]

  # ── What order do I execute? ──
  mutation_sequencing:
    - order: 1
      phase: "read"
      operation: "list"
      description: "Read current active shopping list to check for duplicates."
    - order: 2
      phase: "mutate"
      operation: "create"
      description: "Add the item if no duplicate detected. If duplicate, present options per conflict_analysis_rules."
    - order: 3
      phase: "read"
      operation: "list"
      description: "Verify item was added (read_after_write)."

  # ── How do I prove it worked? ──
  verification_requirements:
    - method: "read_after_write"
      description: "Read back the shopping list and confirm the new item appears with correct name and quantity."
      required_for_submit: true
    - method: "output_schema"
      description: "Validate the returned item matches the expected schema."

  # ── Summaries (injected into Back's prompt) ──
  precondition_summary: >
    Before adding an item, I MUST list the active shopping list to check for
    duplicates. Shopping is a shared family resource — anyone can add, anyone
    can mark purchased. I present duplicate conflicts to the user rather than
    silently creating a second entry.
  companion_resource_summary: >
    Shopping is self-contained — no cross-connector dependencies. Other
    connectors (calendar, chores) may suggest shopping items to the user,
    but shopping itself does not need to coordinate with them.
  hil_trigger_summary: >
    I need human input when: item name or quantity is missing, or a duplicate
    item is detected on the active list.
  degradation_policy: >
    If read_after_write verification fails, retry once then submit degraded.
```

### Issue 13.2 — Shopping Policy + Guide Cards + Ontology

- **Manifest:** `snapshot_types: ["daily_snapshot"]` — shopping appears in daily lookups only (not weekly — shopping lists aren't time-window-specific enough for a weekly overview).

- **Policy:** Shopping lists are shared family resources — all roles can add, update, and mark purchased. No operation is restricted. The only nuance: marking items as "purchased" (which removes them from the active list) is AMBER to prevent accidental clearing. No protected resources.

  ```yaml
  policy_declarations:
    operation_role_gates:
      create_item: ["parent", "child", "guardian"]
      update_item: ["parent", "child", "guardian"]
      mark_purchased: ["parent", "child", "guardian"]
      delete_item: ["parent", "child", "guardian"]
    operation_safety_bands:
      create_item: "GREEN"
      update_item: "GREEN"
      mark_purchased: "AMBER"
      delete_item: "AMBER"
  ```

- **Guide cards:** Two cards: general shopping list management best practices, and how to handle duplicates.

  ```yaml
  guide_cards:
    - guide_id: "family.shopping.guide.01"
      title: "How to Manage the Family Shopping List"
      content: |
        The family shopping list is a shared resource — everyone adds to it,
        everyone marks items as purchased.

        Best practices:
        1. Always LIST the active list before adding — avoid duplicates.
        2. Be specific: "2% milk - half gallon" not just "milk".
        3. Include quantity: "bananas (6)", "paper towels (2-pack)".
        4. Note preferences: "gluten-free bread", "Riley's favorite yogurt".
        5. Group-related items: if adding multiple baking items, mention it.
        6. Mark items purchased when bought — keeps the list clean.
        7. Don't delete purchased items — they become purchase history.

        The shopping list is NOT a todo list. For "remember to go shopping",
        use family.tasks. For "buy milk every Tuesday", consider
        family.chores (recurring) or family.reminders (notification).
      relevance: "always"
      disclosure_phase: "connector_summary"

    - guide_id: "family.shopping.guide.02"
      title: "Duplicate Items — Add or Update?"
      content: |
        When the user says "add milk" and milk is already on the list:

        ASK what they want:
        - "Add anyway" → create a separate entry (they may want 2 half-gallons
          from different stores, or one for today and one for later)
        - "Update quantity" → change existing item qty from 1 to 2
        - "Skip" → do nothing

        DEFAULT guidance: if the duplicate has the SAME specifics (same brand,
        same size), suggest updating quantity. If the duplicate has DIFFERENT
        specifics ("whole milk" vs "2% milk"), treat as different items —
        add separately without asking.

        Never silently skip. The user said to add something — either do it
        or explain why you're not doing it.
      relevance: "on_conflict"
      disclosure_phase: "tool_name_selection"
  ```

- **Ontology:** `concept_aliases`: "groceries"→"shopping_item", "buy"→"shopping_item", "shopping list"→"shopping_item", "purchase"→"shopping_item", "errand"→"shopping_item", "supplies"→"shopping_item". `resource_connector_edges`: `{resource_family: "shopping_item", connector_id: "family.shopping", role: "primary"}`. Note: no companion edges — shopping is a leaf node. `operation_aliases`: "add"→create_item, "buy"→mark_purchased, "purchased"→mark_purchased, "got it"→mark_purchased, "need"→create_item, "pick up"→mark_purchased.

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
| Reminders | `reminder` | create, list, update, delete | duplicate time+person+message, invalid_event_ref, calendar_event dependency, task distinct_sibling | Self-or-parent delete/update, all GREEN safety |
| Chores | `chore` | create, complete, verify, redeem, list, update, delete | duplicate title+assignee+frequency, time_overlap with calendar (advisory), workload_balance (advisory), 4-stage gamification lifecycle | Parent-only assign/verify, child can complete+redeem, AMBER on redeem >$10 |
| Shopping | `shopping_item` | create, list, update, delete, mark_purchased | duplicate item name with resolution guidance, empty companions (leaf node) | All roles can add/update/purchase, AMBER on mark_purchased+delete |

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

---

# Phase 2 — Back Actor Tool Contract Migration

> **Milestone:** GATE-P2 — Back LLM resolves situations, enforces constitutions, and executes bound capabilities on live kernel.
> **Predecessor:** Phase 1.1 (GATE-P1.1 must pass first)
> **Successor:** Phase 3 — Front LLM prompt redesign + dispatch redesign (TBD)
> **Scope:** Epics 15–18. Touches Back actor, Back prompt, Back tool schemas, session wiring, and integration tests.
> **Design source:** `docs/whiteboard/back_tool_contract_whiteboard.md`, `docs/api/back_tool_contract_v2_COMPONENT_MAP.md`, `k1/docs/future_work/front_llm_read_k1surface.md`

---

## Architecture Context: What Changes and Why

**Today (legacy model):**

```
Back receives task → discover_capabilities(query) → top-K catalog results →
  invoke_capability(capability_name) → CapabilityFabric → NativeToolProvider
```

Problems:

- Back does its own capability discovery (brittle keyword match, no constitution enforcement)
- No temporal/spatial/selfmodel context in Back's prompt
- `resolve_situation` exists but Back can't call it (not in tool schemas)
- Back prompt teaches "discover then choose" — wrong mental model for a worker

**Target (Phase 2):**

```
Back receives task → resolve_situation(RequestFrame) → ResolutionEnvelope {
    ResourceUniverse, PolicyBundle, BindingBundle,
    PromptPack, verdict, allowed_capability_names, allowed_next_actions
  } → Back chooses from allowed_capability_names → invoke_capability(binding_id, ...)
```

- Back calls ONE tool (`resolve_situation`) that does ALL discovery, policy gating, constitution enforcement
- `discover_capabilities` kept as fallback (not primary)
- Temporal, spatial, selfmodel, grounding all reach Back's prompt via unified execution context block
- Back prompt teaches "read the envelope, pick from allowed, execute, submit"

---

## Key File Touch Points — Phase 2 At a Glance

| File | Epic 15 | Epic 16 | Epic 17 | Epic 18 | What Changes |
|------|---------|---------|---------|---------|-------------|
| `k1/concierge/session.py` | ✅ | — | — | — | `_back_consumer()` passes `temporal`, `spatial`, `selfmodel` to `route_back_envelope()` |
| `k1/concierge/actors/back_router.py` | ✅ | — | — | — | `route_back_envelope()` signature gains `temporal`, `spatial`, `selfmodel` params |
| `k1/concierge/actors/back.py` | ✅ | ✅ | — | — | `back_handler()` gains `temporal`, `spatial`, `selfmodel` params; `_build_execution_grounding_block()` extended; `_filter_back_tools()` adds `resolve_situation` |
| `k1/concierge/prompt/back_prompt.py` | ✅ | ✅ | ✅ | — | `build_back_prompt()` gains temporal/spatial/selfmodel blocks; `available_tools_note` updated; prompt fully redesigned |
| `k1/concierge/tools/schemas_back.py` | — | ✅ | — | — | `resolve_situation` schema added; `BACK_TIER_ALLOWLISTS` updated; `discover_capabilities` kept as fallback |
| `k1/fabric/fabric.py` | — | ✅ | — | — | `_handle_resolve_situation()` verified for Back dispatcher call path |
| `k1/concierge/react/back_execution_plan.py` | — | ✅ | — | — | May need `resolve_situation` execution item; TBD during discovery |
| `k1/kernel/service.py` | ✅ | — | — | — | Reference only — P3.5-P3.8 already creates temporal/spatial/grounding/selfmodel handles |
| `k1/concierge/factory.py` | ✅ | — | — | — | Reference only — `PortBundle` already wires to `ConciergeRuntime` |
| `k1/temporal/adapters/session_state_adapter.py` | ✅ | — | — | — | Verify temporal handle is accessible for Back prompt rendering |
| `k1/spatial/adapters/session_state_adapter.py` | ✅ | — | — | — | Verify spatial handle is accessible for Back prompt rendering |
| `tests/k1/concierge/actors/test_back_resolve_situation_live.py` | — | — | — | ✅ | New — end-to-end integration gate |

---

## Epic 15: Context Plumbing — Temporal, Spatial, SelfModel, Grounding → Back

**Goal:** Mirror Front LLM's context path for Back. Today only `grounding` reaches Back (via `_back_consumer()` → `route_back_envelope()` → `back_handler()` → `_build_execution_grounding_block()`). Temporal, spatial, and selfmodel handles exist on `ConciergeRuntime` but are never passed to Back's handler or injected into Back's prompt.

---

### 🔍 DISCOVERY COMPLETE (2026-06-09) — What Exists vs. What's Missing

**Four subagents explored every file in `k1/temporal/`, `k1/spatial/`, `k1/selfmodel/`, `k1/grounding/`, `k1/concierge/session.py`, `k1/concierge/actors/back.py`, `k1/concierge/actors/front.py`, `k1/kernel/service.py`.**

---

#### Discovered Handle APIs

| Handle | File | Key Method for Prompt Injection | "Back" Consumer Supported? |
|--------|------|-------------------------------|---------------------------|
| **TemporalHandle** | `k1/temporal/kernel/handle.py:23` | `get_projection(consumer)` → `TemporalProjection` → `render_execution_block(projection)` | ✅ `consumer="back"` works. `render_execution_block()` already exists at `k1/temporal/service/projection_renderer.py:41` |
| **SpatialHandle** | `k1/spatial/kernel/handle.py:20` | `get_projection(consumer)` → `SpatialProjection` | ✅ `consumer="back"` works. `DEFAULT_CONSUMER_PRECISION` already has `"back": "semantic"` at `k1/spatial/constants.py:62` |
| **GroundingHandle** | `k1/grounding/kernel/handle.py:145` | `get_projection(consumer)` → `GroundingProjection` | ✅ Already wired. `_build_execution_grounding_block()` calls `grounding.get_projection("back")` at `back.py:158` |
| **SelfModelHandle** | `k1/selfmodel/kernel/handle.py:66` | `render_capsule()` → `GroundingCapsule` → `.as_prompt_text()` | ⚠️ `render_capsule()` exists but only Front calls it (`front.py:1433`). Back never calls it. |

**Key finding:** ALL four handles already have "get context for actor" methods. Temporal + Spatial use `get_projection(consumer="back")`. SelfModel uses `render_capsule()`. Grounding already works. **No new API methods need to be created on the handles.**

---

#### Discovered ConciergeRuntime Storage

| Handle | Runtime Attribute | Setter Method | Stored? |
|--------|------------------|---------------|---------|
| `temporal` | `self._temporal` | `set_temporal(handle)` — `session.py:297` | ✅ YES |
| `spatial` | `self._spatial` | `set_spatial(handle)` — `session.py:308` | ✅ YES |
| `grounding` | `self._grounding` | `set_grounding(handle)` — `session.py:319` | ✅ YES |
| `self_model` | `self._self_model` | `set_self_model(handle)` — `session.py:330` | ✅ YES |

**Key finding:** ALL four handles are already stored on `ConciergeRuntime`. The kernel already calls `concierge.set_self_model(session_self_model)` at `service.py:3022`. **No new setters or attributes needed on ConciergeRuntime.**

---

#### Discovered Front vs Back Consumer Wiring

| What's Passed | `_front_consumer()` at `session.py:404` | `_back_consumer()` at `session.py:461` |
|---------------|----------------------------------------|---------------------------------------|
| `temporal=self._temporal` | ✅ Yes | ❌ **MISSING** |
| `spatial=self._spatial` | ✅ Yes | ❌ **MISSING** |
| `grounding=self._grounding` | ✅ Yes | ✅ Yes |
| `self_model=self._self_model` | ✅ Yes | ❌ **MISSING** |

```python
# session.py:404 — Front consumer (WHAT WE MIRROR)
await front_handler(
    ...,
    temporal=self._temporal,      # ← handle
    spatial=self._spatial,        # ← handle
    grounding=self._grounding,    # ← handle
    self_model=self._self_model,  # ← handle
)

# session.py:461 — Back consumer (THE GAP)
await route_back_envelope(
    ...,
    grounding=self._grounding,    # ← ONLY grounding
    # NO temporal, NO spatial, NO self_model
)
```

---

#### Discovered Handler Signatures

| Parameter | `front_handler()` at `front.py:1145` | `back_handler()` at `back.py:940` | `back_resume_handler()` at `back.py:1236` |
|-----------|--------------------------------------|-----------------------------------|------------------------------------------|
| `temporal` | ✅ `temporal: Any = None` | ❌ Missing | ❌ Missing |
| `spatial` | ✅ `spatial: Any = None` | ❌ Missing | ❌ Missing |
| `grounding` | ✅ `grounding: Any = None` | ✅ `grounding: Any = None` | ❌ Missing |
| `self_model` | ✅ `self_model: Any = None` | ❌ Missing | ❌ Missing |

---

#### Discovered Front's Actual Context Usage (What Back Should Mirror)

**Temporal in Front:**

- Front does NOT directly build a temporal context block from `TemporalHandle`
- Front's `grounding.refresh_turn()` internally pulls temporal + spatial data
- Fallback: If `grounding is None`, Front calls `temporal.refresh_turn()` + `temporal.build_projection(consumer="front")` at `front.py:1311-1324`
- The rendered `== NOW ==` block comes from `DynamicPromptBuilder._build_now_block(ss)` which reads the temporal section from SessionState (written by `TemporalStateAdapter`)

**Spatial in Front:**

- Front does NOT directly access `SpatialHandle` at all
- Spatial context is mediated entirely through Grounding: `grounding.refresh_turn()` → `GroundingProjection.spatial` → `SpatialProjection`
- Rendered into prompt via `render_place_block()` / `render_place_and_device_block_v2()` from `k1/grounding/service/prompt_block_renderer.py`

**SelfModel in Front:**

- `front_handler` calls `self_model.render_capsule()` → `GroundingCapsule` at `front.py:1433`
- Capsule passed to `DynamicPromptBuilder.build(grounding_capsule=grounding_capsule)` for Stage 9.5 prompt injection

**Back currently:**

- Gets NO live temporal handle (only `resolved_temporal_refs` from task dispatch payload)
- Gets NO live spatial handle at all
- Gets NO self_model capsule in prompt
- `_build_execution_grounding_block()` at `back.py:140` tries task payload grounding first, falls back to `grounding.get_projection("back")` — this is correct but covers only grounding, not the other three

---

#### Discovered: self_model Already Gates back_dispatcher

`SelfModelHandle.install_into_session()` at `selfmodel/kernel/handle.py:90` already:

1. Installs `ConciergePolicyGate` on `back_dispatcher` (line 104-117) — ✅ tool gating works
2. Wraps `back_ctx.recall_fn` with `RecallCitationWrapper` — ✅ recall citations work
3. Does NOT inject `GroundingCapsule` into Back's prompt — ❌ missing

The kernel calls this at `service.py:3005`:

```python
session_self_model.install_into_session(
    front_dispatcher=...,
    back_dispatcher=...,     # ← Back dispatcher IS wired for policy gating
    front_ctx=...,
    back_ctx=...,            # ← Back context IS wired for recall wrapping
)
```

---

#### The Fix: Exactly 3 Lines in `_back_consumer()`, 3 Params in `route_back_envelope()`, 3 Params in `back_handler()`

The change is mechanically simple — add the THREE missing params to mirror Front's path:

```
session.py:    _back_consumer()          + temporal, spatial, self_model → route_back_envelope()
back.py:       route_back_envelope()     + temporal, spatial, self_model → back_handler()
back.py:       back_handler()            + temporal, spatial, self_model → build_back_prompt()
back_prompt.py: build_back_prompt()      + temporal_block, spatial_block, selfmodel_block → BACK_SYSTEM_PROMPT
```

**No new API methods, no new ConciergeRuntime attributes, no new kernel wiring needed.** All four handles already exist, are stored, and have methods that return prompt-ready data.

---

#### Design Decision: Separate Blocks vs. Unified Block

**Recommendation: Keep separate blocks.** The handles produce different types of context:

- `render_execution_block(temporal_projection)` → "== TEMPORAL CONTEXT ==" (deadlines, windows, resolved times)
- Spatial → "== SPATIAL CONTEXT ==" (device location, home, places)
- `render_capsule()` → "== SELFMODEL ==" (preferences, patterns, persona)
- Existing `_build_execution_grounding_block()` → "== EXECUTION GROUNDING ==" (combined grounding projection)

Separate blocks give Back clearer signal. The prompt template already has a "SESSION CONTEXT" section that can hold all four.

---

### Issue 15.1 — Wire Temporal/Spatial/SelfModel Through Back Consumer

- **Files:** `k1/concierge/session.py` lines 461-470, `k1/concierge/actors/back.py` lines 1661-1677
- **What:** Add 3 params to `_back_consumer()` → `route_back_envelope()` → `back_handler()` chain.
- **Concrete change in `session.py` `_back_consumer()`:**

  ```python
  await route_back_envelope(
      envelope=back_env,
      model=self._model,
      ss=self._session_state,
      bus=self._bus,
      tool_dispatcher=self._back_dispatcher,
      fsm_state=self._fsm,
      hil_port=self._hil_port,
      grounding=self._grounding,
      temporal=self._temporal,        # ← NEW
      spatial=self._spatial,          # ← NEW
      self_model=self._self_model,    # ← NEW
  )
  ```

- **Concrete change in `back.py` `route_back_envelope()`:** Add `temporal: Any = None`, `spatial: Any = None`, `self_model: Any = None` to signature. Forward to `back_handler()`. Also forward to `back_resume_handler()` for consistency.
- **Risk:** LOW — all three are `Optional` with default `None`. Existing callers (tests) don't break. The handles already exist on `ConciergeRuntime` and are `None`-safe.

### Issue 15.2 — Extend back_handler() Signature

- **File:** `k1/concierge/actors/back.py` line 940
- **What:** `back_handler()` gains `temporal: Any = None`, `spatial: Any = None`, `self_model: Any = None` params. Passed through to `build_back_prompt()` and `_build_execution_grounding_block()`.
- **Also:** `back_resume_handler()` at line 1236 gains same params for consistency (suspended task resumes get stale context otherwise).

### Issue 15.3 — Build Temporal Context Block for Back Prompt

- **File:** `k1/concierge/actors/back.py` — new function `_build_temporal_context_block()`
- **What:** Calls `temporal.get_projection("back")` → `render_execution_block(projection)` to produce a `str` block.
- **Implementation sketch:**

  ```python
  async def _build_temporal_context_block(temporal: Any | None, task: dict) -> str:
      if temporal is None:
          return ""
      try:
          projection = await temporal.get_projection("back")
          from k1.temporal.service.projection_renderer import render_execution_block
          return render_execution_block(projection)
      except Exception:
          logger.warning("back_handler: temporal context block failed", exc_info=True)
          return ""
  ```

- **Existing renderer:** `render_execution_block(projection)` at `k1/temporal/service/projection_renderer.py:41` — already built, tested, and used by other paths. Just needs to be called from Back.
- **Note:** TemporalHandle caches projections per-consumer. `get_projection("back")` is a cached convenience wrapper over `build_projection(consumer="back")`.

### Issue 15.4 — Build Spatial Context Block for Back Prompt

- **File:** `k1/concierge/actors/back.py` — new function `_build_spatial_context_block()`
- **What:** Calls `spatial.get_projection("back")` → formats into a `str` block.
- **Implementation sketch:**

  ```python
  async def _build_spatial_context_block(spatial: Any | None, task: dict) -> str:
      if spatial is None:
          return ""
      try:
          projection = await spatial.get_projection("back")
          # SpatialProjection → prompt text. Mirror grounding's pattern:
          # grounding/service/prompt_block_renderer.py already has
          # render_place_block() and render_place_and_device_block_v2()
          # that accept GroundingProjection. For standalone spatial, we
          # may need a simpler formatter or reuse Grounding's renderers
          # by constructing a minimal GroundingProjection wrapper.
          return _format_spatial_projection_for_back(projection)
      except Exception:
          logger.warning("back_handler: spatial context block failed", exc_info=True)
          return ""
  ```

- **Discovery needed:** `SpatialProjection` has fields like `current_location`, `device_location`, `home_location`, `nearby_places`. Decide which fields Back needs for execution decisions. Simpler than grounding — Back probably only needs device location + home.

### Issue 15.5 — Build SelfModel Context Block for Back Prompt

- **File:** `k1/concierge/actors/back.py` — new function `_build_selfmodel_context_block()`
- **What:** Calls `self_model.render_capsule()` → `capsule.as_prompt_text()`.
- **Implementation sketch:**

  ```python
  async def _build_selfmodel_context_block(self_model: Any | None) -> str:
      if self_model is None:
          return ""
      try:
          capsule = self_model.render_capsule()
          if capsule is None:
              return ""
          # GroundingCapsule.as_prompt_text() returns the persona/self text
          return capsule.as_prompt_text() if hasattr(capsule, "as_prompt_text") else str(capsule)
      except Exception:
          logger.warning("back_handler: selfmodel context block failed", exc_info=True)
          return ""
  ```

- **This is the EXACT same pattern Front uses** at `front.py:1433`: `grounding_capsule = self_model.render_capsule()`.
- **What Back gets:** Persona preferences, known patterns about the user, self-model constitution rules. This tells Back "the user prefers morning appointments" or "the user is vegan" — context that affects execution decisions.

### Issue 15.6 — Inject New Context Blocks into build_back_prompt()

- **File:** `k1/concierge/prompt/back_prompt.py` lines 411-494
- **What:** `build_back_prompt()` gains `temporal_context_block: str = ""`, `spatial_context_block: str = ""`, `selfmodel_context_block: str = ""` params.
- **Template change:** `BACK_SYSTEM_PROMPT` gains three placeholders in the `== SESSION CONTEXT ==` section:

  ```
  == SESSION CONTEXT ==
  {temporal_context_block}
  {spatial_context_block}
  {selfmodel_context_block}
  {execution_grounding_block}
  Beliefs: {beliefs_summary}
  Active tasks: {task_state_summary}
  Completed artifacts: {artifacts_summary}
  Safety band: {safety_band}
  User preferences: {persona_prefs}
  ```

- **Empty blocks render as nothing** — backward compatible when handles are `None`.
- **Decision:** Separate blocks (not unified). Rationale: each handle produces a different type of context with different headers, and keeping them separate lets Back distinguish "the user prefers..." (selfmodel) from "the current time is..." (temporal) from "you are at..." (spatial).

### Issue 15.7 — Verify Full Context Chain End-to-End

- **File:** New test — `tests/k1/concierge/actors/test_back_context_wiring.py`
- **Test:** `test_temporal_reaches_back_prompt` — mock `TemporalHandle`, verify `render_execution_block` output appears in prompt
- **Test:** `test_spatial_reaches_back_prompt` — mock `SpatialHandle`, verify spatial block appears in prompt
- **Test:** `test_selfmodel_reaches_back_prompt` — mock `SelfModelHandle.render_capsule()`, verify capsule text appears in prompt
- **Test:** `test_grounding_still_reaches_back_prompt` — regression: existing grounding block still works
- **Test:** `test_all_four_contexts_in_prompt` — combined smoke test with all handles
- **Test:** `test_handles_none_still_works` — all handles `None` → prompt builds without errors (backward compat)
- **Run:** `pytest tests/k1/concierge/actors/test_back_context_wiring.py -v`

### Issue 15.1 — Wire Temporal/Spatial/SelfModel Through Back Consumer

- **Files:** `k1/concierge/session.py`, `k1/concierge/actors/back_router.py`
- **What:** `_back_consumer()` passes `temporal=self._temporal`, `spatial=self._spatial`, `selfmodel=self._self_model` to `route_back_envelope()`. `route_back_envelope()` signature updated.
- **Discovery needed:** Does `ConciergeRuntime` have a `_self_model` attribute? Check `session.py` to see how `session_self_model.install_into_session()` stores the handle. The self_model may need to be stored as `self._self_model` in `set_self_model()`.
- **Risk:** Medium — changing Back consumer signature may affect tests that mock `route_back_envelope`.

### Issue 15.2 — Extend back_handler() Signature

- **File:** `k1/concierge/actors/back.py`
- **What:** `back_handler()` gains `temporal`, `spatial`, `selfmodel` params (all `Optional`). These are passed through to `build_back_prompt()`.
- **Note:** `back_resume_handler()` may also need these for consistency; TBD during discovery.

### Issue 15.3 — Build Temporal Context Block for Back Prompt

- **File:** `k1/concierge/actors/back.py` (or new helper in `k1/concierge/prompt/`)
- **What:** `_build_temporal_context_block(temporal_handle, task_payload) -> str` renders Back-facing temporal context:
  - Current time + timezone from `TemporalHandle`
  - Relevant temporal anchors from the task's `temporal_anchor_id`
  - Resolved time expressions from `resolved_temporal_refs` (already in task payload)
- **Discovery needed:** Read `TemporalHandle` API to understand what `get_context_for_actor("back")` or equivalent method exists. May need to add a Back-specific context method.
- **Reference:** Front LLM gets temporal context from `_extract_family_context(ss)` — but Front reads persona/preferences, not raw temporal anchors. Back needs different temporal data (execution-oriented: deadlines, windows, recurrence).

### Issue 15.4 — Build Spatial Context Block for Back Prompt

- **File:** `k1/concierge/actors/back.py` (or new helper)
- **What:** `_build_spatial_context_block(spatial_handle, task_payload) -> str` renders Back-facing spatial context:
  - Device location from `SpatialHandle`
  - Household location context
  - Relevant spatial anchors from the task's `spatial_context_id`
- **Discovery needed:** Read `SpatialHandle` API. Is there a `get_context_for_actor("back")` method? What spatial data is relevant for Back's execution decisions?

### Issue 15.5 — Build SelfModel Context Block for Back Prompt

- **File:** `k1/concierge/actors/back.py` (or new helper)
- **What:** `_build_selfmodel_context_block(selfmodel_handle, session_id, principal_id) -> str` renders Back-facing selfmodel context:
  - Persona preferences relevant to task execution
  - Known user patterns (e.g., "user prefers morning appointments", "user always buys organic")
  - Policy gates already installed via `install_into_session()`
- **Discovery needed:** Read `SelfModelHandle` API. What data does it expose for prompt injection? Does it have `get_prompt_context()` or similar? The `install_into_session()` path gates `back_dispatcher` — we need the prompt-injection path in addition.

### Issue 15.6 — Inject New Context Blocks into build_back_prompt()

- **File:** `k1/concierge/prompt/back_prompt.py`
- **What:** `build_back_prompt()` gains `temporal_context_block`, `spatial_context_block`, `selfmodel_context_block` params. `BACK_SYSTEM_PROMPT` gains `{temporal_context_block}`, `{spatial_context_block}`, `{selfmodel_context_block}` placeholders in the SESSION CONTEXT section.
- **Discovery needed:** Decide whether to keep separate blocks or merge into one `{execution_context_block}`. Separate blocks give Back clearer signal about where each piece of context comes from. Merged block is simpler. TBD during discovery.

### Issue 15.7 — Verify Full Context Chain End-to-End

- **File:** New test — `tests/k1/concierge/actors/test_back_context_wiring.py`
- **Test:** `test_temporal_reaches_back_prompt` — verify temporal block appears in built prompt
- **Test:** `test_spatial_reaches_back_prompt` — verify spatial block appears in built prompt
- **Test:** `test_selfmodel_reaches_back_prompt` — verify selfmodel block appears in built prompt
- **Test:** `test_grounding_still_reaches_back_prompt` — regression: grounding block still works
- **Test:** `test_all_four_contexts_in_prompt` — combined smoke test
- **Run:** `pytest tests/k1/concierge/actors/test_back_context_wiring.py -v`

---

## Epic 16: Tool Contract Migration — Register resolve_situation as Back Tool

**Goal:** Make `resolve_situation` the PRIMARY tool Back calls to understand what to do. Keep `discover_capabilities` as fallback. The `resolve_situation` meta-tool already exists in Fabric (`_handle_resolve_situation()` at `k1/fabric/fabric.py:1757`). It just needs to be registered as a Back-callable tool.

---

### 🔍 DISCOVERY COMPLETE (2026-06-09) — How Tools Reach Fabric

**Four subagents explored the complete Back tool dispatch chain: ToolDispatcher, TOOL_REGISTRY, implementations.py, FabricDispatchAdapter, Fabric, ResolveSituationService.**

---

#### Discovered: Back Already Reaches Fabric via `ctx.dispatch`

```
Back LLM tool_call
  → ToolDispatcher.dispatch()                    [dispatcher.py:477, 7-step pipeline]
    → execute_tool(name, args, ctx)              [implementations.py:2037, dict lookup]
      → TOOL_REGISTRY["discover_capabilities"]   [@_register decorator, implementations.py:1361]
        → ctx.dispatch.discover_capabilities()   [IDispatchPort method]
          → FabricDispatchAdapter                [adapters/fabric_dispatch.py:369]
            → self._fabric.discover_capabilities()  [IFabricPort = Fabric container]
              → Fabric.retrieval → RetrievalEngine  [4-step semantic pipeline]
```

**The `FabricDispatchAdapter` stores `self._fabric`** (the actual `Fabric` container instance). Back's `ToolDispatcher` stores `self.ctx.dispatch` → `FabricDispatchAdapter` → `self._fabric`. The chain is:

```
ToolDispatcher → ToolContext → FabricDispatchAdapter → Fabric container → situated_resolver
```

**Key finding: NO new Fabric wiring is needed.** The `Fabric._handle_resolve_situation()` method already exists at `fabric.py:1757`. The `ResolveSituationService` is already wired into Fabric's `situated_resolver` attribute at `FabricFactory._wire_phase1_stores()` (`factory.py:1101`). Back just needs a tool that calls it.

---

#### Discovered: How Tools Are Registered (The Pattern)

Tools follow a **4-step registration pattern**:

| Step | What | Where | Example |
|------|------|-------|---------|
| 1 | Define `ToolSchema` | `schemas_back.py` (or `schemas_fabric.py` for shared) | `BATCH_INVOKE_CAPABILITIES_SCHEMA` at line 38 |
| 2 | Add to schema list | `BACK_TOOL_SCHEMAS` list | `schemas_back.py:251` |
| 3 | Add to tier allowlist | `BACK_TIER_ALLOWLISTS` dict | `schemas_back.py:260-274` |
| 4 | Register handler | `implementations.py` via `@_register("name")` | `@_register("discover_capabilities")` at line 1361 |

**`TOOL_REGISTRY`** is a flat `dict[str, callable]` at `implementations.py:137`. Every tool handler is a key in this dict. There is no meta-tool concept, no routing table — it's a simple dict lookup via `execute_tool()` at line 2037:

```python
async def execute_tool(tool_name, args, ctx):
    fn = TOOL_REGISTRY.get(tool_name)    # ← simple dict lookup
    result = fn(args, ctx)
    if inspect.isawaitable(result):
        result = await result
    return result
```

**Architecture: Only ONE path to the LLM.** Steps 1-3 above (schema → list → allowlist) feed into `_filter_back_tools()` → `react_loop(tools=...)` → `tools` array (function-calling definitions). This is what the LLM sees — a JSON array of `{name, description, parameters}` objects, identical to how Front receives tools (see `front_prompt_latest.json`). Step 4 (`@_register`) feeds into `TOOL_REGISTRY` — the BACKEND dispatch table, never seen by the LLM. There is no second path, no meta-tool registration system. The `available_tools_note` in the system prompt is just guidance prose — it does NOT register tools.

---

#### Discovered: The Fabric Dispatch Path We Need

Back currently uses TWO patterns to reach Fabric:

| Pattern | Handler Calls | Fabric Method | Used By |
|---------|--------------|---------------|---------|
| **Dedicated method** | `ctx.dispatch.discover_capabilities()` | `Fabric.discover_capabilities()` via `FabricDispatchAdapter.discover_capabilities()` | discover_capabilities |
| **General dispatch** | `ctx.dispatch.dispatch_direct(CapabilityRequest(...))` | `Fabric.execute()` via `FabricDispatchAdapter.dispatch_direct()` | invoke_capability |

**For `resolve_situation`, we need a THIRD pattern** — a dedicated dispatch method:

```python
# In implementations.py — the handler
@_register("resolve_situation")
async def execute_resolve_situation(args: dict, ctx: ToolContext) -> ToolResult:
    payload = _build_resolve_payload(args, ctx)
    result = await ctx.dispatch.resolve_situation(payload)
    return ToolResult(status="ok", data=result)

# In FabricDispatchAdapter — the adapter method (NEW)
async def resolve_situation(self, payload: dict) -> dict:
    return await self._fabric._handle_resolve_situation(payload)
```

**`IDispatchPort`** (the protocol at `ports.py:106`) currently has: `discover_capabilities`, `lookup_capability`, `dispatch_direct`, `dispatch_envelope`. We add `resolve_situation`.

---

#### Discovered: What Fields Back LLM Controls vs. What's Auto-Filled

`_build_resolve_request()` at `fabric.py:1889` deserializes the payload dict → `ResolveSituationRequest`. Required keys: `actor_id`, `space_id`, `session_id`, `frame`.

| Field | Source | LLM-Visible? |
|-------|--------|-------------|
| `actor_id` | `ctx.session_manager` → session principal | ❌ Auto-filled |
| `space_id` | `ctx.active_space_id` or `"family:default"` | ❌ Auto-filled |
| `session_id` | `ctx.active_session_id` | ❌ Auto-filled |
| `request_id` | Generated UUID | ❌ Auto-filled |
| `tier` | `ctx.active_task_tier` or `"MEDIUM"` | ❌ Auto-filled (from task) |
| `safety_band` | `ctx.safety_band` or `"GREEN"` | ❌ Auto-filled (from task) |
| **`frame`** | LLM provides via JSON Schema | ✅ **LLM controls** |
| `disclosure_phase` | `"connector_summary"` default, LLM can override | ⚠️ Optional override |
| `freshness_policy` | `"allow_stale_reads"` default, LLM can override | ⚠️ Optional override |
| `prompt_budget_tokens` | `8000` default, LLM can override | ⚠️ Optional override |
| `idempotency_keys` | LLM provides if needed | ⚠️ Optional |
| `completed_prerequisite_bindings` | Dispatcher tracks from prior calls | ❌ Auto-filled |
| `previous_resolution_id` | Dispatcher tracks | ❌ Auto-filled |
| `budget_remaining` | From budget tracker | ❌ Auto-filled |

**The JSON Schema Back's LLM sees should expose:**

- **Required:** `frame` (with `intents`, `time_window_hint`, `person_refs`, `resource_refs`, `safety_context` sub-fields)
- **Optional:** `idempotency_keys`, `disclosure_phase`, `freshness_policy`, `prompt_budget_tokens`

---

#### Discovered: What Back Gets Back (ResolutionEnvelope)

`ResolutionEnvelope` at `situated_resolver.py:87` has 20 fields. The `to_dict()` returns:

```json
{
  "verdict": "can_execute",
  "machine_verdict": "can_execute",
  "sub_reason": null,
  "allowed_capability_names": ["tool.execute.family.calendar.create"],
  "allowed_next_actions": ["create a calendar event for Riley..."],
  "capability_name_to_binding": {"tool.execute.family.calendar.create": "bind-abc123"},
  "execution_plan": [{
    "step": 1, "type": "prerequisite_read",
    "capability_name": "tool.read.family.calendar.list",
    "required_inputs": [...]
  }, {
    "step": 2, "type": "primary_write",
    "capability_name": "tool.execute.family.calendar.create",
    "required_inputs": [{"name": "title", "type": "string"}, ...]
  }],
  "hil_request": null,
  "recovery_directive": null,
  "diagnostics": [...],
  "completeness": "full",
  "freshness": "fresh",
  "binding_bundle": {...},
  "policy_bundle": {...},
  "constitution": {...},
  "prompt_pack": {...}
}
```

**This is the complete surface Back's LLM reads to decide what to do.** The `allowed_capability_names` list is the ONLY capabilities Back can invoke. The `execution_plan` tells Back the order (prerequisite reads first, then writes, then verifications).

---

#### Current Back Tools (7 schemas, all in schemas_back.py:251)

| # | Tool | Source | Category |
|---|------|--------|----------|
| 1 | `recall_memory` | `schemas_front.py:355` (imported) | read |
| 2 | `discover_capabilities` | `schemas_fabric.py:27` (imported) | read |
| 3 | `invoke_capability` | `schemas_fabric.py:95` (imported) | action |
| 4 | `batch_invoke_capabilities` | `schemas_back.py:38` | action |
| 5 | `spawn_via_fabric` | `schemas_back.py:99` | action |
| 6 | `execute_workflow` | `schemas_back.py:149` | action |
| 7 | `submit_result` | `schemas_back.py:197` | control |

**`BACK_TIER_ALLOWLISTS`** at `schemas_back.py:260-274`: `simple`/`LOW` = tools 1-5+7; `plan`/`MEDIUM`/`HIGH` = all 7. MEDIUM and HIGH are identical for Back tools.

**`_filter_back_tools()`** at `back.py:216`: Looks up tier in allowlist, filters `BACK_TOOL_SCHEMAS` by name membership. Unknown tiers fall back to `["submit_result"]` only.

---

### Issue 16.1 — Add resolve_situation Tool Schema

- **File:** `k1/concierge/tools/schemas_back.py`, after `BATCH_INVOKE_CAPABILITIES_SCHEMA` (~line 97)
- **What:** Define `RESOLVE_SITUATION_SCHEMA` as a new `ToolSchema`:

  ```python
  RESOLVE_SITUATION_SCHEMA = ToolSchema(
      name="resolve_situation",
      description=(
          "PRIMARY TOOL — call this FIRST for every task. "
          "Resolves what capabilities are available, checks policies, "
          "enforces constitution rules, and returns exactly which "
          "actions you are allowed to perform. "
          "Returns a ResolutionEnvelope with verdict, allowed_capability_names, "
          "allowed_next_actions, execution_plan, and prompt_pack."
      ),
      parameters={
          "type": "object",
          "properties": {
              "frame": {
                  "type": "object",
                  "description": "The task frame with intents, time windows, person/ resource refs",
                  "required": ["intents"],
                  "properties": {
                      "intents": {
                          "type": "array",
                          "description": "What the user wants done. Each intent has action, domain, operation_hint, resource_kind_hint, subject_hint, params",
                          "items": {
                              "type": "object",
                              "properties": {
                                  "action": {"type": "string", "description": "Natural language action e.g. 'schedule', 'buy', 'remind'"},
                                  "domain": {"type": "string", "description": "e.g. 'family', 'health', 'finance'"},
                                  "operation_hint": {"type": "string", "description": "e.g. 'create', 'read', 'update', 'delete'"},
                                  "resource_kind_hint": {"type": "string", "description": "e.g. 'calendar_event', 'task', 'shopping_item'"},
                                  "subject_hint": {"type": "string", "description": "Who or what this is about"},
                                  "params": {"type": "object", "description": "Additional parameters"}
                              },
                              "required": ["action"]
                          }
                      },
                      "time_window_hint": {
                          "type": "object",
                          "description": "Time expressions from the user request",
                          "properties": {
                              "raw_phrase": {"type": "string"},
                              "resolved_start": {"type": "string"},
                              "resolved_end": {"type": "string"}
                          }
                      },
                      "person_refs": {
                          "type": "array",
                          "description": "People mentioned in the request",
                          "items": {"type": "object", "properties": {"raw": {"type": "string"}, "needs_resolution": {"type": "boolean"}}}
                      },
                      "resource_refs": {
                          "type": "array",
                          "description": "Resources mentioned in the request",
                          "items": {"type": "object", "properties": {"raw": {"type": "string"}, "resource_kind_hint": {"type": "string"}, "needs_resolution": {"type": "boolean"}}}
                      },
                      "safety_context": {
                          "type": "object",
                          "description": "Safety band and overrides",
                          "properties": {"safety_band": {"type": "string", "enum": ["GREEN", "AMBER", "RED"]}}
                      }
                  }
              },
              "idempotency_keys": {
                  "type": "array", "items": {"type": "string"},
                  "description": "Optional keys for deduplication"
              },
              "disclosure_phase": {
                  "type": "string",
                  "enum": ["connector_summary", "capability_names_only", "full_disclosure"],
                  "description": "How much detail to return. Default: connector_summary"
              },
              "freshness_policy": {
                  "type": "string",
                  "enum": ["strict_freshness", "allow_stale_reads", "bypass_freshness"],
                  "description": "How strict to be about data freshness. Default: allow_stale_reads"
              },
              "prompt_budget_tokens": {
                  "type": "integer", "minimum": 500, "maximum": 32000,
                  "description": "Max tokens for the prompt_pack. Default: 8000"
              }
          },
          "required": ["frame"]
      },
      returns={"type": "object", "description": "ResolutionEnvelope with verdict, allowed_capability_names, allowed_next_actions, execution_plan, prompt_pack"},
      category="read",
      side_effects=False,
      actor="back",
  )
  ```

- **Add to `BACK_TOOL_SCHEMAS`** list as FIRST entry (line 251):

  ```python
  BACK_TOOL_SCHEMAS: list[ToolSchema] = [
      RESOLVE_SITUATION_SCHEMA,           # NEW — primary resolution tool
      RECALL_MEMORY_SCHEMA,
      DISCOVER_CAPABILITIES_SCHEMA,
      ...
  ]
  ```

### Issue 16.2 — Add resolve_situation to Back Tool Allowlists

- **File:** `k1/concierge/tools/schemas_back.py` lines 260-274
- **What:** Add `"resolve_situation"` as FIRST entry in `_BACK_SIMPLE_LIST`:

  ```python
  _BACK_SIMPLE_LIST: list[str] = [
      "resolve_situation",          # ← NEW — primary tool, always available
      "recall_memory",
      "discover_capabilities",
      "invoke_capability",
      "batch_invoke_capabilities",
      "submit_result",
  ]
  ```

- **`plan`/MEDIUM/HIGH automatically inherit it** via `_BACK_SIMPLE_LIST + _BACK_PLAN_EXTRA`.

### Issue 16.3 — Register resolve_situation Handler in implementations.py

- **File:** `k1/concierge/tools/implementations.py` — new handler after `execute_discover_capabilities` (~line 1465)
- **What:** Register `@_register("resolve_situation")` handler that builds payload + calls dispatch:

  ```python
  @_register("resolve_situation")
  async def execute_resolve_situation(args: dict, ctx: ToolContext) -> ToolResult:
      """Resolve a task situation via Fabric's situated resolver.

      Auto-fills identity/session fields from ToolContext. The LLM
      only provides the frame (intents, time_window, person_refs, etc.)
      and optional overrides.
      """
      try:
          import uuid as _uuid

          # ── Build payload: auto-fill identity, LLM provides frame ──
          frame = args.get("frame", {})
          payload = {
              "actor_id": str(getattr(ctx, "active_principal_id", "") or ""),
              "space_id": str(getattr(ctx, "active_space_id", "") or "family:default"),
              "session_id": str(getattr(ctx, "active_session_id", "") or ""),
              "tier": str(getattr(ctx, "active_task_tier", "") or "MEDIUM"),
              "safety_band": str(getattr(ctx, "safety_band", "") or "GREEN"),
              "frame": frame,
              "request_id": "req-" + _uuid.uuid4().hex[:12],
          }

          # Optional LLM overrides
          for key in ("disclosure_phase", "freshness_policy",
                       "prompt_budget_tokens", "idempotency_keys"):
              if key in args:
                  payload[key] = args[key]

          # ── Dispatch to Fabric ──
          if not hasattr(ctx.dispatch, "resolve_situation"):
              return ToolResult(
                  status="error",
                  data={"verdict": "cannot_execute",
                        "sub_reason": "resolve_situation_not_wired",
                        "message": "Fabric dispatch adapter does not support resolve_situation"}
              )

          result = await ctx.dispatch.resolve_situation(payload)
          return ToolResult(status="ok", data=result)
      except Exception as exc:
          return ToolResult(
              status="error",
              data={"verdict": "cannot_execute",
                    "sub_reason": "handler_exception",
                    "message": str(exc)}
          )
  ```

### Issue 16.4 — Add resolve_situation to IDispatchPort + FabricDispatchAdapter

- **Files:** `k1/concierge/ports.py` line 106, `k1/concierge/adapters/fabric_dispatch.py` line 34
- **What:** Add `resolve_situation` to the protocol and adapter:

  ```python
  # ports.py — IDispatchPort protocol (add method)
  async def resolve_situation(self, payload: dict) -> dict: ...

  # fabric_dispatch.py — FabricDispatchAdapter (add method ~line 92)
  async def resolve_situation(self, payload: dict) -> dict:
      """Route resolve_situation to Fabric's PUBLIC resolve_situation() method.

      🔴 PORT/ADAPTER FIX: Calls self._fabric.resolve_situation(request)
      (public port method at fabric.py:1740), NOT the private
      _handle_resolve_situation(). Deserializes dict to
      ResolveSituationRequest internally.
      """
      if not hasattr(self._fabric, "resolve_situation"):
          return {"verdict": "cannot_execute", "sub_reason": "handler_not_available"}
      try:
          from k1.fabric.types import ResolveSituationRequest
          request = _build_resolve_request_from_payload(payload)
          envelope = self._fabric.resolve_situation(request)  # PUBLIC port
          return envelope.to_dict()
      except Exception as exc:
          return {"verdict": "cannot_execute", "sub_reason": "handler_exception",
                  "diagnostics": [{"type": "handler_error", "error": str(exc)}]}
  ```

- **Risk:** LOW — `resolve_situation` is optional (the handler checks `hasattr`). If the adapter doesn't support it, Back gets a clear `cannot_execute` verdict with `resolve_situation_not_wired` reason.

### Issue 16.5 — Update available_tools_note in Back Prompt

- **File:** `k1/concierge/prompt/back_prompt.py` — `build_back_prompt()` lines 455-480
- **What:** Replace the hardcoded tool-name lists with guidance-only prose. **The LLM already knows WHAT tools it has from the `tools` array (function-calling definitions auto-generated from `BACK_TOOL_SCHEMAS` + allowlist).** The `available_tools_note` should only teach HOW to use them — order, strategy, rules.

  ```python
  # BEFORE (bad — hardcoded tool names, redundant with function definitions):
  available_tools_note = (
      "YOUR AVAILABLE TOOLS (LOW tier): recall_memory, discover_capabilities, "
      "invoke_capability, batch_invoke_capabilities, submit_result.\n"
      "You do NOT have spawn_via_fabric or execute_workflow.\n"
      "PREFER batch_invoke_capabilities when invoking 2+ capabilities."
  )

  # AFTER (good — guidance only, no tool name lists):
  available_tools_note = (
      "TOOL USAGE ORDER:\n"
      "  1. resolve_situation — ALWAYS first. Understand what you can do.\n"
      "  2. recall_memory — ONLY for historical context the dispatch lacks.\n"
      "  3. invoke / batch_invoke — Execute what resolve_situation allows.\n"
      "  4. discover_capabilities — FALLBACK ONLY. Use when resolve_situation\n"
      "     cannot find a capability.\n"
      "  5. submit_result — ALWAYS last. The only way to finish.\n"
      "\n"
      "PREFER batch_invoke_capabilities for 2+ independent invocations.\n"
      "Copy capability names EXACTLY from resolve_situation's output.\n"
      "Never guess or invent capability names."
  )
  ```

- **No tier differentiation needed** — the same guidance applies to LOW, MEDIUM, and HIGH. The LLM's `tools` array automatically reflects tier differences (e.g., `spawn_via_fabric` only appears in MEDIUM+ tiers via allowlist filtering).
- **Architecture note:** There is only ONE path for tools to reach the LLM: `BACK_TOOL_SCHEMAS` → `_filter_back_tools(tier)` → `react_loop(tools=...)` → `tools` array (function-calling definitions). `TOOL_REGISTRY` is the backend handler dispatch table (not LLM-facing). `available_tools_note` is guidance prose in the system prompt (not a tool registration path).

### Issue 16.6 — Verify resolve_situation Works from Back Dispatcher

- **File:** New test — `tests/k1/concierge/actors/test_back_resolve_situation_tool.py`
- **Test:** `test_resolve_situation_schema_valid` — schema parses with `ToolSchema` fields correct
- **Test:** `test_resolve_situation_in_simple_allowlist` — appears in `_BACK_SIMPLE_LIST`
- **Test:** `test_resolve_situation_in_back_schemas` — appears in `BACK_TOOL_SCHEMAS`
- **Test:** `test_resolve_situation_handler_registered` — `TOOL_REGISTRY["resolve_situation"]` exists
- **Test:** `test_resolve_situation_auto_fills_identity` — handler populates `actor_id`, `space_id`, `session_id` from `ToolContext`
- **Test:** `test_resolve_situation_calls_fabric_adapter` — mock `ctx.dispatch.resolve_situation()` called with expected payload
- **Test:** `test_resolve_situation_returns_envelope_dict` — returns `ToolResult(status="ok")` with `verdict` key
- **Test:** `test_resolve_situation_unwired_returns_error` — when `ctx.dispatch` lacks `resolve_situation`, returns error envelope
- **Test:** `test_discover_capabilities_still_works` — regression: fallback tool still functional
- **Run:** `pytest tests/k1/concierge/actors/test_back_resolve_situation_tool.py -v`

### Issue 16.7 — Add Batch Names Lookup to discover_capabilities

- **File:** `k1/concierge/tools/schemas_fabric.py` — `DISCOVER_CAPABILITIES_SCHEMA`
- **File:** `k1/concierge/tools/implementations.py` — `execute_discover_capabilities`
- **What:** Add an optional `names: list[str]` parameter to `discover_capabilities`. When Back passes explicit capability names, skip semantic search entirely and use O(1) exact lookup via `registry.lookup(name)` for each name. Returns all matching schemas in a single batch response.

**Problem this solves (GAP-P2-032):** When Back resolves a situation and the constitution lists companion resources (e.g., calendar's constitution says "list chores for soft conflict check"), Back knows the EXACT companion tool names (`tool.read.chores.list_chores`, `tool.read.tasks.list_tasks`) but has no way to get their input schemas in one call. Without batch lookup, Back must either:

1. Call `discover_capabilities(intent="list chores")` once per companion tool — slow, heuristic-dependent, fragile (BM25 may not match the exact name).
2. Guess the params from the tool name — unsafe.

**Schema extension:**

```json
{
  "name": "discover_capabilities",
  "parameters": {
    "properties": {
      "intent": {"type": "string", "description": "Natural language query (use empty string when names is provided)."},
      "domain": {"type": "string", "description": "Domain hint to narrow search."},
      "names": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Exact capability names for batch deterministic schema lookup. When provided, skips semantic search and returns schemas for each name via O(1) exact match. USE THIS when the constitution or a prior resolution tells you the EXACT companion tool names (e.g., tool.read.chores.list_chores). Returns score=1.0 for found names; silently omits missing names."
      },
      "constraints": {"type": "object", "description": "Capability requirements."}
    },
    "required": ["intent"]
  }
}
```

**Handler logic (in execute_discover_capabilities, before semantic search):**

```python
# NEW: batch deterministic lookup via exact capability names
names: list[str] | None = args.get("names")
if names:
    caps: list[dict[str, Any]] = []
    for name in names:
        contract = await _lookup_capability_contract_exact(ctx, name)
        if contract is not None:
            caps.append({
                "name": name,
                "description": getattr(contract, "description", ""),
                "domain": (contract.domain[0] if contract.domain else ""),
                "domains": list(contract.domain) if contract.domain else [],
                "score": 1.0,  # deterministic exact match
                "prompt_template": str(getattr(contract, "prompt_template", "") or ""),
                "activity_profile": str(getattr(contract, "activity_profile", "") or ""),
                "tool_instructions": str(getattr(contract, "tool_instructions", "") or ""),
                "limitations": list(getattr(contract, "limitations", ()) or ()),
                "schema": _capability_prompt_schema(contract),
            })
    return ToolResult(
        tool_name="discover_capabilities",
        status="ok",
        data={"capabilities": caps, "count": len(caps)},
    )

# else: existing semantic search path (unchanged)
intent = args.get("intent", "")
...
```

**Design decisions:**
- `names` takes priority: when provided, semantic search is skipped entirely.
- `intent` remains `required` in the schema for backward compatibility; Back passes a non-empty placeholder (e.g., `"companion tool lookup"`) when using `names`.
- Score = 1.0 for exact name matches (deterministic, not heuristic).
- Missing names are silently omitted (Back already knows the name; if it's missing, the contract is gone — a hard error).
- No per-session caching for batch names (O(1) lookups are too cheap to warrant cache complexity).

**Risk:** LOW — additive parameter, existing semantic search path unchanged. The `_lookup_capability_contract_exact` helper already handles `dispatch.lookup(name)` and `dispatch.lookup_capability(name)` fallbacks.

### Issue 16.8 — Tests: discover_capabilities Batch Names

- **File:** New test — `tests/k1/concierge/tools/test_discover_capabilities_batch_names.py`
- **Test:** `test_batch_names_returns_schemas_for_valid_names` — three real capability names → three schemas returned, all score=1.0
- **Test:** `test_batch_names_omits_missing_name` — one valid + one nonexistent name → valid returned, missing silently omitted
- **Test:** `test_batch_names_skips_semantic_search` — when `names` provided, `ctx.dispatch.discover_capabilities` is NEVER called (verified via mock assertion)
- **Test:** `test_batch_names_backward_compat_semantic_still_works` — calling without `names` still performs semantic search (regression)
- **Test:** `test_batch_names_empty_list_returns_empty` — `names=[]` → empty capabilities, no error
- **Test:** `test_batch_names_calendar_companion_scenario` — simulate Back asking for calendar companion tools: `names=["tool.read.chores.list_chores", "tool.read.tasks.list_tasks", "tool.read.reminders.list_reminders"]` → all three schemas returned with correct required_inputs
- **Test:** `test_batch_names_contract_has_input_schema` — each returned capability has `schema.required_inputs` and `schema.optional_inputs` populated from the real `CapabilityContract`
- **Run:** `pytest tests/k1/concierge/tools/test_discover_capabilities_batch_names.py -v`

---

## Epic 17: Back Prompt Redesign — resolve_situation-First Model

**Goal:** Rewrite `BACK_SYSTEM_PROMPT` to teach Back the `resolve_situation`-first execution model. The current prompt (~250 lines, ~1800 words, 8 sections) teaches "discover capabilities, then choose, then invoke." The new prompt teaches "call resolve_situation, read the envelope, execute what's allowed, submit."

---

### 🔍 DISCOVERY COMPLETE (2026-06-09) — Full Prompt Anatomy + Gap Analysis

**Read every line of `k1/concierge/prompt/back_prompt.py` (530 lines) and `k1/concierge/actors/back.py` lines 326-440 (snapshot) + lines 990-1130 (prompt assembly).**

---

#### How the Prompt Is Formed (End-to-End)

```
back_handler() [back.py:940]
  │
  ├─ 1. _read_ss_snapshot(ss) [back.py:326]
  │     Reads 7 SS sections → returns dict with 7 keys:
  │       beliefs_prompt, referents, task_state_prompt,
  │       task_artifacts_prompt, safety_band, history_entries, persona_prefs
  │
  ├─ 2. _build_execution_grounding_block(task, grounding) [back.py:140]
  │     Tries task payload grounding → live grounding.get_projection("back") → raw fields
  │
  ├─ 3. build_back_prompt(task, beliefs, referents, task_state, task_artifacts,
  │                        safety_band, persona_prefs, max_tool_calls,
  │                        execution_profile_block, execution_grounding_block,
  │                        resolved_temporal_refs) [back_prompt.py:411]
  │     │
  │     ├─ Generates available_tools_note from tier
  │     ├─ Renders resolved_temporal_refs into execution_grounding_block
  │     └─ BACK_SYSTEM_PROMPT.format(task_json=..., beliefs_summary=...,
  │           task_state_summary=..., artifacts_summary=..., safety_band=...,
  │           persona_prefs=..., max_tool_calls=..., execution_profile_block=...,
  │           execution_grounding_block=..., available_tools_note=...)
  │
  └─ 4. Messages = chat history + task as ModelMessage(role="user", content=task_json)
```

**The prompt is a natural language document** with `{variable}` holes filled by Python `.format()`. It reads like prose, not a schema. This is correct — Back is an LLM, not a parser.

---

#### Current Variable Inventory (10 variables)

| # | Variable | Populated From | In Prompt Section |
|---|----------|---------------|-------------------|
| 1 | `{task_json}` | `task` dict → `json.dumps(task, indent=2)` | `== TASK DISPATCH ==` |
| 2 | `{beliefs_summary}` | `snapshot["beliefs_prompt"]` (beliefs_active SS section) | `== SESSION CONTEXT ==` |
| 3 | `{task_state_summary}` | `snapshot["task_state_prompt"]` (task_state SS section) | `== SESSION CONTEXT ==` |
| 4 | `{artifacts_summary}` | `snapshot["task_artifacts_prompt"]` (task_artifacts SS section) | `== SESSION CONTEXT ==` |
| 5 | `{safety_band}` | `_get_safety_band(control SS section)` | `== SESSION CONTEXT ==` |
| 6 | `{persona_prefs}` | `snapshot["persona_prefs"]` (persona SS section → payment/dietary/accessibility) | `== SESSION CONTEXT ==` |
| 7 | `{max_tool_calls}` | Tier config (`back_max_tool_calls`) | `== BUDGET ==` |
| 8 | `{execution_profile_block}` | Activity profile YAML → `_execution_profile_block_for_selection()` | `== REACT EXECUTION PROTOCOL ==` (mid-section, after header) |
| 9 | `{execution_grounding_block}` | Grounding handle or task payload fields | `== REACT EXECUTION PROTOCOL ==` (mid-section, after profile_block) |
| 10 | `{available_tools_note}` | Generated in `build_back_prompt()` from tier | `== TOOL SELECTION RULES ==` |

**Not used but available:** `referents` dict (from scoreboard SS section) is passed to `build_back_prompt()` but has NO `{referents}` placeholder in the template. It's silently ignored.

---

#### Current Prompt Section-by-Section Map

| # | Section | Lines in Template | What It Teaches Back | Verdict |
|---|---------|-------------------|---------------------|---------|
| 1 | `== IDENTITY ==` | ~35 lines | "You are the Worker. Pure executor." What Back IS, is NOT, produces. Built-in knowledge boundaries. | **KEEP** (nearly unchanged) |
| 2 | `== REACT EXECUTION PROTOCOL ==` | ~120 lines | 8-step Think-Act-Observe loop: ORIENT → CHECK → ASSESS → DISCOVER → SAFETY → INVOKE → EVALUATE → SUBMIT. Teaches discover_capabilities as the core workflow. | **REPLACE** (resolve_situation-first protocol) |
| 3 | `== TOOL SELECTION RULES ==` | ~55 lines | Capability naming conventions, domain hints, web search workflow, mandatory tool usage order (recall → discover → invoke → batch → submit). Teaches discover_capabilities as PRIMARY. | **REPLACE** (resolve_situation as primary, discover as fallback) |
| 4 | `== RESULT FORMAT ==` | ~30 lines | submit_result(complete) fields: final_answer, results, artifacts_created, semantic_context. Authority boundaries. | **KEEP** (minor updates for ResolutionEnvelope evidence) |
| 5 | `== AMBIGUITY HANDLING ==` | ~4 lines | Max 2 suspensions. On third: pick best, note reasoning. | **KEEP** (unchanged) |
| 6 | `== ANTI-PATTERNS (NEVER DO THESE) ==` | ~22 lines | 11 NEVER-DO rules: no user-facing text, no re-execution, no capability name invention, no submit before invoke, etc. | **UPDATE** (add resolve_situation rules, remove discover-specific anti-patterns) |
| 7 | `== BUDGET ==` | ~6 lines | `{max_tool_calls}` tool calls remaining. Plan upfront. | **KEEP** (update for resolve_situation cost model) |
| 8 | `== TASK DISPATCH ==` | 1 line | `{task_json}` — the raw task payload as JSON. | **KEEP** (unchanged) |
| 9 | `== SESSION CONTEXT ==` | 5 lines | Beliefs, task_state, artifacts, safety_band, persona_prefs. | **EXPAND** (add temporal, spatial, selfmodel, grounding blocks + scoreboard) |

---

#### Missing Session State: What Back Doesn't Know About

`_read_ss_snapshot()` at `back.py:326` reads 7 SS sections but **explicitly skips**:

| SS Section | Read? | Injected into Prompt? | Should Back Know? |
|------------|-------|----------------------|-------------------|
| `beliefs_active` | ✅ Yes | ✅ `{beliefs_summary}` | — |
| `scoreboard` | ✅ Yes (as `referents` dict) | ❌ **NO `{referents}` placeholder exists** | ✅ Yes — pronoun resolution helps Back understand "she said" / "that task" |
| `task_state` | ✅ Yes | ✅ `{task_state_summary}` | — |
| `task_artifacts` | ✅ Yes | ✅ `{artifacts_summary}` | — |
| `control` | ✅ Yes (safety_band only) | ✅ `{safety_band}` | — |
| `history_active` | ✅ Yes | ❌ (used for chat history, not prompt) | — |
| `persona` | ✅ Yes (payment/dietary/accessibility) | ✅ `{persona_prefs}` | — |
| **`temporal`** | ❌ Explicitly skipped | ❌ | ✅ **YES** — Back needs current time, timezone, windows for execution decisions |
| **`spatial`** | ❌ Never mentioned | ❌ | ✅ **YES** — Back needs device/home location context |
| **`affective_now`** | ❌ Explicitly skipped | ❌ | ❌ No — Front's emotional state, irrelevant to Back |
| **`clarifications`** | ❌ Explicitly skipped | ❌ | ❌ No — Front's concern |
| **`narrative_active`** | ❌ Explicitly skipped | ❌ | ❌ No — Front's thread tracking |

**Gap:** `scoreboard` referents are read but silently dropped. `temporal` and `spatial` SS sections exist but Back never reads them. Epic 15 adds live handle projections for temporal/spatial/selfmodel/grounding — but the SS sections contain DIFFERENT data (e.g., resolved expressions cached from prior turns).

---

#### New Variable Inventory After Epic 17 (13 variables)

| # | Variable | Epic | Source |
|---|----------|------|--------|
| 1-6 | `{task_json}`, `{beliefs_summary}`, `{task_state_summary}`, `{artifacts_summary}`, `{safety_band}`, `{persona_prefs}` | Existing | SS snapshot (unchanged) |
| 7 | `{max_tool_calls}` | Existing | Tier config (unchanged) |
| 8 | `{available_tools_note}` | Epic 16 | Updated: resolve_situation as primary |
| 9 | `{temporal_context_block}` | **Epic 15** | `TemporalHandle.get_projection("back")` → `render_execution_block()` |
| 10 | `{spatial_context_block}` | **Epic 15** | `SpatialHandle.get_projection("back")` → formatted text |
| 11 | `{selfmodel_context_block}` | **Epic 15** | `SelfModelHandle.render_capsule()` → `as_prompt_text()` |
| 12 | `{execution_grounding_block}` | Existing | Grounding handle (unchanged, stays) |
| 13 | `{scoreboard_summary}` | **Epic 17** | `snapshot["referents"]` → formatted text (was read but never injected) |

**Removed:** `{execution_profile_block}` — activity profiles are now guide cards inside the ResolutionEnvelope's prompt_pack. Back no longer needs pre-injected activity guidance; it discovers context through resolve_situation.

---

#### Target Prompt Structure (9 sections)

| # | Section | Status | What It Teaches |
|---|---------|--------|-----------------|
| 1 | `== IDENTITY ==` | KEEP (minor edits) | "You are the Worker." Built-in knowledge boundaries. |
| 2 | `== EXECUTION CONTEXT ==` | **NEW** | `{temporal_context_block}`, `{spatial_context_block}`, `{selfmodel_context_block}`, `{execution_grounding_block}` — Back's live situational awareness. |
| 3 | `== YOUR PRIMARY TOOL: resolve_situation ==` | **NEW** | Teaches Back that `resolve_situation` is ALWAYS step 1. Describes what it does, what it returns. |
| 4 | `== HOW TO READ A RESOLUTION ENVELOPE ==` | **NEW** | Teaches Back the verdict model. Each verdict → what to do next. Not a flowchart — natural language guidance. |
| 5 | `== EXECUTION PROTOCOL ==` | **REPLACE** (was REACT PROTOCOL) | 4-step loop: RESOLVE → EXECUTE → VERIFY → SUBMIT. Much simpler than 8-step discover-then-invoke. |
| 6 | `== TOOL REFERENCE ==` | **REPLACE** (was TOOL SELECTION RULES) | `{available_tools_note}` + tool usage order. resolve_situation first, discover_capabilities as fallback. |
| 7 | `== RESULT FORMAT ==` | KEEP (minor updates) | submit_result fields. Add guidance for including ResolutionEnvelope evidence. |
| 8 | `== GUARDRAILS ==` | **MERGE** (was AMBIGUITY + ANTI-PATTERNS + BUDGET) | Ambiguity limits, anti-patterns, budget rules. Consolidated — Back doesn't need three separate guardrail sections. |
| 9 | `== TASK DISPATCH ==` | KEEP | `{task_json}` |
| 10 | `== SESSION STATE ==` | **EXPAND** (was SESSION CONTEXT) | `{scoreboard_summary}`, `{beliefs_summary}`, `{task_state_summary}`, `{artifacts_summary}`, `{safety_band}`, `{persona_prefs}` |

---

#### Section 4 Design: HOW TO READ A RESOLUTION ENVELOPE

This is the most critical new section. It must teach Back what each verdict means in natural language — NOT as a flowchart or decision tree.

**Design principle:** The verdict names may evolve. Don't hard-code exact strings like `"can_execute_with_gate"` as if they're API enums. Instead, describe the SEMANTICS of each verdict category in natural language, and let the LLM pattern-match the actual verdict string from the envelope.

```
== HOW TO READ A RESOLUTION ENVELOPE ==
When you call resolve_situation, you receive a ResolutionEnvelope with a
"verdict" field. This tells you what you are allowed to do.

EXECUTABLE VERDICTS (you CAN act):
  If the verdict indicates the task can proceed:
    → Look at "allowed_capability_names" — these are the ONLY capability
      names you may invoke. Do not use any other name.
    → Look at "execution_plan" — this is the ordered sequence of steps.
      Typically: prerequisite_read(s) first, then primary_write, then
      optional verification.
    → Look at "allowed_next_actions" — these are natural language
      descriptions of what to do. Use them to understand intent.
    → Invoke the capabilities in order. Use batch_invoke_capabilities
      when multiple steps are independent.
    → When all steps complete: submit_result(complete).

  If the verdict indicates the task can proceed but has a gate:
    → Same as above, but the execution_plan may include a verification
      step. Execute the verification capability AFTER the primary action.
    → The gate may require you to check something before or after.
      Follow the execution_plan order exactly.

BLOCKING VERDICTS (you CANNOT act):
  If the verdict indicates the task is blocked by policy:
    → submit_result(cannot_execute, reason=<copy the sub_reason from envelope>).
    → Do NOT try discover_capabilities. Policy blocks are authoritative.

  If the verdict indicates no capability was found:
    → You MAY try discover_capabilities as a fallback search.
    → If discover also finds nothing: submit_result(cannot_execute).
    → If discover finds something: you may invoke it directly (no need
      to re-call resolve_situation).

HUMAN-IN-THE-LOOP VERDICTS:
  If the verdict indicates the task needs human input:
    → Look at "hil_request" in the envelope for the exact question.
    → Call submit_result(needs_human, questions=[<the question>]).
    → The task will be suspended and resumed after the human responds.

  If the verdict indicates ambiguity (unclear who or what):
    → submit_result(needs_human, clarification=<what needs clarifying>).

STALE DATA VERDICTS:
  If the verdict indicates the projection is stale:
    → Re-call resolve_situation with freshness_policy="bypass_freshness".
    → This tells the resolver to skip cache and get fresh data.
    → Then proceed with the new envelope's verdict.

IDEMPOTENCY:
  If you re-call resolve_situation with the same idempotency_keys,
  you will get the SAME resolution_id. Use this to avoid duplicate work.
```

---

#### Section 5 Design: EXECUTION PROTOCOL (4 Steps)

Replaces the current 8-step REACT EXECUTION PROTOCOL. Much simpler:

```
== EXECUTION PROTOCOL ==
You operate in a 4-step loop. Every task follows this sequence.

STEP 1 — RESOLVE:
  Call resolve_situation(frame={...}) with the task's intents, time windows,
  person references, and resource references from the TASK DISPATCH.
  This is ALWAYS your first tool call. No exceptions.

  The frame should contain:
    - intents: what the user wants done (action, domain, hints)
    - time_window_hint: any time expressions from the request
    - person_refs: people mentioned
    - resource_refs: resources mentioned

  You receive a ResolutionEnvelope. Read the verdict.

STEP 2 — EXECUTE:
  If the verdict allows execution:
    - Follow the execution_plan order.
    - Use ONLY capability names from allowed_capability_names.
    - Copy capability names EXACTLY — they are registry-owned.
    - Batch independent invocations with batch_invoke_capabilities.
    - If a prerequisite_read returns data needed for the primary_write,
      use that data in the write's params.

  If the verdict blocks execution:
    - Follow the envelope's guidance (see HOW TO READ A RESOLUTION ENVELOPE).
    - Do not try to work around a policy block.

STEP 3 — VERIFY (if required):
  If the execution_plan includes a verification step:
    - Execute it after the primary action.
    - If verification fails: the capability's result will indicate recovery.
    - If verification passes: proceed to submit.

STEP 4 — SUBMIT:
  Call submit_result(complete) with:
    - final_answer: factual summary of what was done
    - results: ALL invoke_capability results verbatim
    - artifacts_created: durable outputs
    - Include the resolution_id from the envelope in semantic_context
      so future turns can reference this resolution.
```

---

#### Section 6 Design: TOOL REFERENCE

Replaces the current TOOL SELECTION RULES. Shorter, resolve_situation-first:

```
== TOOL REFERENCE ==
{available_tools_note}

MANDATORY TOOL ORDER:
  1. resolve_situation — ALWAYS first. Call exactly ONCE per task
     (unless the envelope says "stale_projection" — then call again
     with freshness_policy="bypass_freshness").
  2. recall_memory — ONLY for historical context the dispatch lacks.
     Do NOT use for live system-of-record data. Do NOT use as a
     substitute for resolve_situation.
  3. discover_capabilities(names=[...]) — AFTER resolve_situation,
     when the constitution or envelope tells you companion tool names
     (e.g., "list chores for conflict check"), call discover_capabilities
     with the `names` parameter to get their input schemas in ONE batch.
     Pass the EXACT capability names from the constitution verbatim.
     Do NOT call discover_capabilities(intent=...) for this — use `names`.
  4. invoke_capability / batch_invoke_capabilities — Execute allowed
     capabilities. Prefer batch_invoke_capabilities for 2+ calls.
     Copy capability names EXACTLY from allowed_capability_names.
  5. discover_capabilities(intent=...) — FALLBACK ONLY. Use ONLY when
     resolve_situation returns missing_capability and you need to
     search for alternatives. Never call before resolve_situation.
  6. submit_result — ALWAYS at the end. The ONLY way to finish a task.

COMPANION TOOL SCHEMA DISCOVERY:
  When resolve_situation returns a constitution that mentions companion
  tools (e.g., "Before action: list chores for soft conflict check"),
  you MUST discover their schemas before invoking them.  Use:

    discover_capabilities(
      intent="companion tool lookup",
      names=[
        "tool.read.chores.list_chores",
        "tool.read.tasks.list_tasks"
      ]
    )

  This returns ALL schemas in ONE call.  The constitution tells you the
  EXACT companion tool names — copy them verbatim into the `names` array.
  Do NOT call discover_capabilities once per tool; do NOT use the
  `intent`-based search for tools you already know the names of.

CAPABILITY NAMES ARE REGISTRY-OWNED:
  You do not know capability names. resolve_situation tells you the
  exact names in allowed_capability_names. Copy them verbatim.
  Never guess, infer, or construct a capability name.
```

---

### 🔍 CONVERSATION INJECTION DISCOVERY (2026-06-09) — 3 Injections From Existing Data, 1 Deferred

**Three subagents explored `history_active`, `TypedHistoryEntry`, `build_chat_history_for_back`, Front's dispatch_task handler, `TaskDispatch`, and the FSM's history write protocol.**

---

#### Discovery: 3 of 4 Injections Already Have Data In Memory

Back's `_read_ss_snapshot()` at `back.py:326` already loads `history_entries` (list of `TypedHistoryEntry`) into `snapshot["history_entries"]`. This list is currently used ONLY for building `ModelMessage` objects via `build_chat_history_for_back()`. But it contains ALL the data needed for three additional prompt injections — we just never rendered them.

| Injection | Data Source | Status |
|-----------|------------|--------|
| `{triggering_utterance}` | `snapshot["history_entries"]` — last `entry_type == "user"` | ✅ Data exists in memory |
| `{conversation_prefix}` | `snapshot["history_entries"]` — last `entry_type == "final"` | ✅ Data exists in memory |
| `{recent_history}` | `snapshot["history_entries"]` — last N entries of types `"user"`, `"final"`, `"hitl_response"` | ✅ Data exists in memory |
| `{front_checks}` | Front's `ToolDispatcher.call_history` — garbage collected after react_loop | ❌ Data does NOT persist |

---

#### Grounded Code Paths — What Exists Today

**FSM's `_write_history()`** at `controller.py:1701` writes these entry types to `controller.history` (the richest source):

| entry_type | text content | role | Written when |
|-----------|-------------|------|-------------|
| `"user"` | Raw user input message | `"user"` | User speaks (`_on_user_input`) |
| `"final"` | Front's conversational response | `"assistant"` | Front responds (`_on_response_final`) |
| `"weave"` | Async result presentation | `"assistant"` | Weave delivery |
| `"proactive"` | Proactive fill delivery | `"assistant"` | Proactive delivery |
| `"hitl_request"` | HITL question string | `"assistant"` | Task suspended |
| `"hitl_response"` | User's HITL answer | `"user"` | Task resumed |
| `"task_complete"` | Back task completed | `"system"` | Back finishes |
| `"error"` / `"cancel_confirmed"` | Task failure/cancel | `"system"` | Back fails |

**`build_chat_history_for_back()`** at `history.py:76` already filters to `"user"`, `"final"`, `"hitl_response"` — but truncates text to 500 chars and returns `ModelMessage` objects. For prompt injection we need the FULL text and a plain-text format.

**Already-existing extraction pattern** in `session.py:619`:

```python
for entry in reversed(self._fsm.history):
    if getattr(entry, "entry_type", None) == "user":
        turn_transcript = entry.text or ""
        break
```

This is the EXACT pattern for extracting `{triggering_utterance}` and `{conversation_prefix}` — just filter for different entry types.

**No new FSM code, no new SS reads, no new TaskDispatch fields needed.** The `snapshot["history_entries"]` list is already loaded in `back_handler` at line 1025. We just need to iterate it and format the text.

---

#### Injection 14: `{triggering_utterance}` — The Raw User Message

**Data:** Last `TypedHistoryEntry` with `entry_type == "user"` from `snapshot["history_entries"]`.

**Extraction (in `back_handler`, ~3 lines):**

```python
def _extract_triggering_utterance(history_entries: list) -> str:
    for entry in reversed(history_entries):
        if getattr(entry, "entry_type", None) == "user":
            return entry.text or ""
    return ""
```

**Why:** The `task_json` contains parsed intents (structured) but not the raw user text. The user might say *"I'm tired of pasta, can you figure out dinner with that salmon from yesterday?"* — Back receives `intents: [{action: "suggest recipes", ...}]` but loses "I'm tired of pasta" (emotional context) and "from yesterday" (freshness concern).

---

#### Injection 15: `{conversation_prefix}` — What Front Told the User

**Data:** Last `TypedHistoryEntry` with `entry_type in ("final", "proactive", "weave")` from `snapshot["history_entries"]`.

**Extraction (in `back_handler`, ~3 lines):**

```python
def _extract_conversation_prefix(history_entries: list) -> str:
    for entry in reversed(history_entries):
        if getattr(entry, "entry_type", None) in ("final", "proactive", "weave"):
            return entry.text or ""
    return ""
```

**Why:** Front may have told the user "Let me check your calendar first... OK, you're free after 6pm. I see salmon in the fridge. Let me find recipes." Back doesn't know Front already checked the calendar — it might re-check unnecessarily. This injection tells Back what the user already knows.

---

#### Injection 16: `{recent_history}` — Full Recent Conversation

**Data:** Last N `TypedHistoryEntry` objects from `snapshot["history_entries"]`, filtered to `"user"`, `"final"`, `"hitl_response"`, rendered as readable text WITHOUT 500-char truncation.

**Renderer (new ~15-line helper in `back.py`):**

```python
def _render_recent_history_for_prompt(entries: list, window: int = 10) -> str:
    """Render recent conversation as readable text for Back's prompt.

    Reuses the same entry-type filter as build_chat_history_for_back()
    (history.py:76) but renders as natural language text instead of
    ModelMessage objects and does NOT truncate to 500 chars.
    """
    relevant = [e for e in entries if getattr(e, "entry_type", None) in ("user", "final", "hitl_response")]
    lines = []
    for entry in relevant[-window:]:
        entry_type = getattr(entry, "entry_type", "")
        text = getattr(entry, "text", "") or ""
        if entry_type == "user":
            lines.append(f"User: {text}")
        elif entry_type == "hitl_response":
            lines.append(f"User (answering question): {text}")
        else:
            lines.append(f"Front: {text}")
        lines.append("")
    return "\n".join(lines)
```

**Existing code reused:**

- Entry type filter: same as `build_chat_history_for_back()` at `history.py:82`
- Role mapping: same as `history_to_back_context()` at `history_writer.py:213`
- The `_ENTRY_PREFIX` dict at `history_writer.py:196` for label ideas

**Why:** The `messages` array (ModelMessage objects) is the primary conversation context for the LLM. But having a readable text summary in the system prompt gives Back a SECOND comprehension path. LLMs process system prompts differently from conversation messages — dual-path context improves understanding. Also removes the 500-char truncation that loses detail.

---

#### Injection 17: `{front_checks}` — DEFERRED to Phase 3

**Why deferred:** Front's tool call history exists in `ToolDispatcher.call_history` / `get_call_summaries()` but is **garbage-collected** after `react_loop()` returns. No FSM history entries are written for Front's tool calls. `TaskDispatch.context_snapshot` exists but is **never populated**. No `front_checks` / `pre_dispatch` / `already_checked` concept exists anywhere in the codebase.

**Three options for Phase 3:**

| Option | What | Effort | Risk |
|--------|------|--------|------|
| A | `front_handler` calls `tool_dispatcher.get_call_summaries()` before dispatching, attaches to payload as new `TaskDispatch.front_tool_summaries` field | Medium | Low |
| B | FSM writes history entries for Front tool calls via `TOPIC_TOOL_STARTED`/`TOPIC_TOOL_COMPLETED` (already emitted at `dispatcher.py:668`) | High | Medium |
| C | Defer entirely — `resolve_situation` handles prerequisite tracking via `completed_prerequisite_bindings` | Zero | None |

**Recommendation: Option C for Phase 2.** The resolver's 13-step cascade already tracks what's been done. Back follows the `execution_plan` — it doesn't need to independently know what Front checked.

---

#### Updated Variable Inventory (10 → 16)

| # | Variable | Epic | Source | New Code Needed? |
|---|----------|------|--------|-----------------|
| 1-6 | `{task_json}`, `{beliefs_summary}`, `{task_state_summary}`, `{artifacts_summary}`, `{safety_band}`, `{persona_prefs}` | Existing | SS snapshot | None |
| 7 | `{max_tool_calls}` | Existing | Tier config | None |
| 8 | `{available_tools_note}` | Epic 16 | Updated | None |
| 9 | `{temporal_context_block}` | Epic 15 | `TemporalHandle.get_projection("back")` | Handle wiring |
| 10 | `{spatial_context_block}` | Epic 15 | `SpatialHandle.get_projection("back")` | Handle wiring |
| 11 | `{selfmodel_context_block}` | Epic 15 | `SelfModelHandle.render_capsule()` | Handle wiring |
| 12 | `{execution_grounding_block}` | Existing | Grounding handle | None |
| 13 | `{scoreboard_summary}` | Epic 17 | `snapshot["referents"]` (was read but never injected) | ~5 line formatter |
| **14** | **`{triggering_utterance}`** | **Epic 17** | **`snapshot["history_entries"]` last `"user"`** | **~3 line extraction** |
| **15** | **`{conversation_prefix}`** | **Epic 17** | **`snapshot["history_entries"]` last `"final"`** | **~3 line extraction** |
| **16** | **`{recent_history}`** | **Epic 17** | **`snapshot["history_entries"]` last N entries** | **~15 line renderer** |
| — | `{front_checks}` | Deferred | Front's dispatcher history (not persisted) | Phase 3 |

**Removed:** `{execution_profile_block}` — activity profiles now delivered via ResolutionEnvelope.prompt_pack.

---

### Issue 17.1 — Map Current Prompt Sections: KEEP / UPDATE / REPLACE / NEW

- **File:** `k1/concierge/prompt/back_prompt.py` lines 41-315 (`BACK_SYSTEM_PROMPT` constant)
- **What:** Section-by-section audit of the current 250-line prompt. Every line mapped to KEEP, UPDATE, REPLACE, or NEW.
- **Map (see table above in "Current Prompt Section-by-Section Map"):**
  - KEEP (minor edits): IDENTITY, RESULT FORMAT, TASK DISPATCH
  - REPLACE: REACT EXECUTION PROTOCOL → EXECUTION PROTOCOL, TOOL SELECTION RULES → TOOL REFERENCE
  - MERGE: AMBIGUITY + ANTI-PATTERNS + BUDGET → GUARDRAILS
  - NEW: EXECUTION CONTEXT, YOUR PRIMARY TOOL: resolve_situation, HOW TO READ A RESOLUTION ENVELOPE
  - EXPAND: SESSION CONTEXT → SESSION STATE (add scoreboard + Epic 15 blocks)

### Issue 17.2 — Write New BACK_SYSTEM_PROMPT

- **File:** `k1/concierge/prompt/back_prompt.py` — replace `BACK_SYSTEM_PROMPT` constant
- **What:** Full rewrite as a natural language document with `{variable}` fill-in-the-blanks. Same `.format()` substitution pattern. New structure:
  1. `== IDENTITY ==` — KEEP (minor: remove "You are NOT aware of who the user is" since selfmodel now provides persona context)
  2. `== EXECUTION CONTEXT ==` — NEW — `{temporal_context_block}`, `{spatial_context_block}`, `{selfmodel_context_block}`, `{execution_grounding_block}`
  3. `== YOUR PRIMARY TOOL: resolve_situation ==` — NEW — teaches Back this is ALWAYS step 1
  4. `== HOW TO READ A RESOLUTION ENVELOPE ==` — NEW — verdict semantics in natural language
  5. `== EXECUTION PROTOCOL ==` — REPLACE — 4-step RESOLVE→EXECUTE→VERIFY→SUBMIT
  6. `== TOOL REFERENCE ==` — REPLACE — `{available_tools_note}` + mandatory order
  7. `== RESULT FORMAT ==` — KEEP (add: include resolution_id in semantic_context)
  8. `== GUARDRAILS ==` — MERGE — ambiguity limits + anti-patterns + budget
  9. `== TASK DISPATCH ==` — KEEP — `{task_json}`
  10. `== SESSION STATE ==` — EXPAND — `{scoreboard_summary}`, `{beliefs_summary}`, `{task_state_summary}`, `{artifacts_summary}`, `{safety_band}`, `{persona_prefs}`
- **Design constraint:** The prompt must be a natural language document. No flowcharts, no pseudo-code, no structured schemas. Back is an LLM — teach it in prose.
- **Variable naming convention:** Keep existing variable names unchanged where possible. New variables follow the same `{snake_case}` convention.
- **Risk:** HIGH — this is the core behavioral change. Must be tested with Epic 18 integration gate.

### Issue 17.3 — Update build_back_prompt() Signature + Logic

- **File:** `k1/concierge/prompt/back_prompt.py` lines 411-494 (`build_back_prompt()`)
- **What:** Update function signature and body for new variables:

  ```python
  def build_back_prompt(
      task: dict[str, Any],
      beliefs: str = "",
      referents: dict[str, Any] | None = None,
      task_state: str = "",
      task_artifacts: str = "",
      safety_band: str = "GREEN",
      persona_prefs: dict[str, Any] | None = None,
      max_tool_calls: int | None = None,
      # ── Epic 15: New context blocks ──
      temporal_context_block: str = "",       # NEW
      spatial_context_block: str = "",         # NEW
      selfmodel_context_block: str = "",       # NEW
      # ── Existing, kept ──
      execution_grounding_block: str = "",
      resolved_temporal_refs: dict[str, Any] | None = None,
      # ── REMOVED: execution_profile_block (now in prompt_pack) ──
  ) -> str:
  ```

- **Changes:**
  - ADD: `temporal_context_block`, `spatial_context_block`, `selfmodel_context_block` params
  - REMOVE: `execution_profile_block` param (activity profiles now delivered via ResolutionEnvelope.prompt_pack)
  - ADD: `scoreboard_summary` generation from `referents` dict (was passed but never used)
  - SIMPLIFY: `available_tools_note` — no longer hardcoded tool-name lists per tier. Single guidance prose block teaching tool ORDER (not names). The LLM already knows WHAT tools it has from the `tools` array (function-calling definitions auto-generated from `BACK_TOOL_SCHEMAS` + allowlist). See Issue 16.5.
  - UPDATE: `.format()` call with new placeholder names
- **Backward compatibility:** All new params default to `""`. Existing callers that don't pass them get empty blocks.

### Issue 17.4 — Update _read_ss_snapshot() to Include Scoreboard Summary

- **File:** `k1/concierge/actors/back.py` lines 326-440 (`_read_ss_snapshot()`)
- **What:** Add `scoreboard_summary` to the returned dict. Currently `referents` are read but silently dropped because no `{referents}` placeholder exists in the old prompt.

  ```python
  return {
      "beliefs_prompt": ...,
      "referents": _get_referents(scoreboard),
      "scoreboard_summary": _render_scoreboard_for_back(scoreboard),  # NEW
      "task_state_prompt": ...,
      ...
  }
  ```

- **`_render_scoreboard_for_back()`** — new helper that formats scoreboard referents as a brief text block:

  ```
  Referents: {"she" → "Riley (daughter)", "that task" → "Buy groceries (task-abc123)", ...}
  ```

- **Why:** Back currently can't resolve pronouns. If the task says "remind her about that", Back has no idea who "her" is or what "that" refers to. Scoreboard has this resolution.

### Issue 17.5 — Wire New Context Blocks into back_handler()

- **File:** `k1/concierge/actors/back.py` lines 1060-1098 (prompt assembly section)
- **What:** After Epic 15 wires `temporal`, `spatial`, `self_model` into `back_handler()`, build the three context blocks and pass them to `build_back_prompt()`:

  ```python
  # After Epic 15: temporal, spatial, self_model are available as params
  temporal_block = await _build_temporal_context_block(temporal, task)
  spatial_block = await _build_spatial_context_block(spatial, task)
  selfmodel_block = await _build_selfmodel_context_block(self_model)

  system_prompt = build_back_prompt(
      task=task,
      beliefs=snapshot["beliefs_prompt"],
      ...
      temporal_context_block=temporal_block,      # NEW
      spatial_context_block=spatial_block,          # NEW
      selfmodel_context_block=selfmodel_block,      # NEW
      # REMOVED: execution_profile_block=...       # No longer passed
      execution_grounding_block=execution_grounding_block,
      resolved_temporal_refs=resolved_temporal_refs,
  )
  ```

- **Note:** The `execution_profile_block` param is REMOVED from the `build_back_prompt()` call. Activity profiles now arrive via `ResolutionEnvelope.prompt_pack` when Back calls `resolve_situation`.

### Issue 17.6 — Verify Prompt Coherence + Regression

- **File:** New test — `tests/k1/concierge/prompt/test_back_prompt_redesign.py`
- **Tests:**
  - `test_all_placeholders_resolve` — `.format()` with all 13 variables, no `KeyError`
  - `test_prompt_contains_resolve_situation_guidance` — "resolve_situation" appears in PRIMARY TOOL and TOOL REFERENCE sections
  - `test_prompt_contains_envelope_reading_guide` — verdict semantics described in natural language
  - `test_prompt_contains_context_blocks` — temporal/spatial/selfmodel/grounding placeholders present
  - `test_prompt_contains_scoreboard` — `{scoreboard_summary}` placeholder present
  - `test_old_discover_first_language_removed` — "call discover_capabilities" NOT in STEP 1 position
  - `test_discover_is_fallback_only` — "discover_capabilities" only appears in FALLBACK context
  - `test_prompt_length_under_4096_tokens` — fits in model context with room for task + envelope
  - `test_new_variables_default_to_empty` — passing `""` for new blocks produces valid prompt
  - `test_existing_variables_still_work` — `task_json`, `beliefs_summary`, etc. still inject correctly
  - `test_execution_profile_block_removed` — `{execution_profile_block}` no longer in template
  - `test_backward_compat_old_call_signature` — calling with old params (no new blocks) still works
- **Run:** `pytest tests/k1/concierge/prompt/test_back_prompt_redesign.py -v`

### Issue 17.7 — Build Conversation Injections from Existing snapshot["history_entries"]

- **File:** `k1/concierge/actors/back.py` — new extraction helpers (~25 lines total)
- **What:** Three small functions that extract text from `snapshot["history_entries"]` (already in memory — zero new data reads):
  1. `_extract_triggering_utterance(history_entries)` — last `entry_type == "user"` text (~3 lines)
  2. `_extract_conversation_prefix(history_entries)` — last `entry_type in ("final", "proactive", "weave")` text (~3 lines)
  3. `_render_recent_history_for_prompt(history_entries, window=10)` — last N `"user"`/`"final"`/`"hitl_response"` entries as readable text, no truncation (~15 lines)
- **Existing code reused:**
  - Entry type filter from `build_chat_history_for_back()` at `history.py:82`
  - Extraction pattern from `session.py:619` (`reversed(history)` + `entry_type` check)
  - Role label mapping from `history_to_back_context()` at `history_writer.py:213`
- **Why window=10:** Back currently gets only 3-5 chat history entries (as messages). For prompt text, we can afford more — 10 entries gives Back roughly 5 full conversation turns of context without truncation.
- **Risk:** LOW — all three functions are pure text extraction from data already in memory. No I/O, no state mutation.

### Issue 17.8 — Wire Conversation Injections into build_back_prompt()

- **File:** `k1/concierge/prompt/back_prompt.py` — `build_back_prompt()` signature
- **What:** Add three new params:

  ```python
  def build_back_prompt(
      ...,
      triggering_utterance: str = "",       # NEW — Issue 17.7
      conversation_prefix: str = "",         # NEW — Issue 17.7
      recent_history: str = "",              # NEW — Issue 17.7
  ) -> str:
  ```

- **Template additions:** `BACK_SYSTEM_PROMPT` gains three placeholders in the `== SESSION STATE ==` section (or a new `== CONVERSATION CONTEXT ==` section):

  ```
  == CONVERSATION CONTEXT ==
  {triggering_utterance}
  {conversation_prefix}
  {recent_history}
  ```

- **Default behavior:** All three default to `""` — empty blocks render as nothing. Backward compatible.

### Issue 17.9 — Wire Conversation Injections into back_handler()

- **File:** `k1/concierge/actors/back.py` — prompt assembly section (~line 1060)
- **What:** Call the three extraction functions and pass results to `build_back_prompt()`:

  ```python
  history_entries = snapshot["history_entries"]
  triggering_utterance = _extract_triggering_utterance(history_entries)
  conversation_prefix = _extract_conversation_prefix(history_entries)
  recent_history = _render_recent_history_for_prompt(history_entries, window=10)

  system_prompt = build_back_prompt(
      task=task,
      ...,
      triggering_utterance=triggering_utterance,        # NEW
      conversation_prefix=conversation_prefix,            # NEW
      recent_history=recent_history,                      # NEW
  )
  ```

### Issue 17.10 — Verify Conversation Injections

- **File:** New tests in `tests/k1/concierge/prompt/test_back_prompt_redesign.py`
- **Tests:**
  - `test_triggering_utterance_extracted` — last `"user"` entry text appears in prompt
  - `test_conversation_prefix_extracted` — last `"final"` entry text appears in prompt
  - `test_recent_history_rendered` — last N entries rendered as "User: ...\nFront: ..."
  - `test_recent_history_not_truncated` — text longer than 500 chars preserved
  - `test_no_user_entry_returns_empty` — empty history → empty blocks
  - `test_backward_compat_no_new_params` — calling without new params still works

---

## Epic 18: Integration Gate — Prove Back Executes on Live Kernel

**Goal:** End-to-end test proving Back can receive a task, call `resolve_situation` via LLM, read the `ResolutionEnvelope`, invoke a bound capability, and submit a complete result. This is the GATE-P2 proof — Back + Fabric + Kernel working together.

**Test scenario:**

```
User utterance: "Add dentist appointment for Riley next Monday at 3pm"
  → Front LLM → dispatch_task → FSM → Back (LOW tier)
  → Back LLM calls resolve_situation(task_frame)
  → ResolveSituationService executes 13-step cascade
  → ResolutionEnvelope {
      verdict: "can_execute",
      allowed_capability_names: ["tool.execute.family.calendar.create"],
      allowed_next_actions: [{
        action: "create a calendar event",
        capability: "tool.execute.family.calendar.create",
        required_inputs: [...]
      }],
      prompt_pack: PromptPack(summary="Create dentist appointment...")
    }
  → Back LLM calls invoke_capability("tool.execute.family.calendar.create", {...})
  → CapabilityFabric → NativeToolProvider → CalendarService → event created
  → Back LLM calls submit_result(complete, final_answer="Created dentist appointment...")
  → FSM → WeavePolicy → Front: "Done! Riley has a dentist appointment Monday at 3pm."
```

### Issue 18.1 — Build Integration Test Fixture

- **File:** `tests/k1/concierge/actors/test_back_resolve_situation_live.py`
- **What:** Test fixture that:
  1. Starts a minimal kernel with Fabric stores enabled (`KernelConfig.enable_fabric_stores=True`)
  2. Registers Calendar connector with full constitution (from Epic 9)
  3. Creates a session with temporal/spatial/grounding/selfmodel handles
  4. Wires Back actor with `resolve_situation` in tool allowlist
  5. Provides a mock model backend that returns realistic LLM responses (or uses a real model for live testing)
- **Discovery needed:** What's the minimal kernel subset needed? Can we reuse `tests/k1/fabric/` fixtures? Does Back need a real LLM or can we use a scripted response pattern?

### Issue 18.2 — Test: resolve_situation → can_execute → invoke → complete

- **File:** `tests/k1/concierge/actors/test_back_resolve_situation_live.py`
- **Test:** `test_back_calendar_create_happy_path`
  - Given: task dispatch for "Add dentist appointment for Riley next Monday at 3pm"
  - When: Back handler processes the task
  - Then: `resolve_situation` returns `can_execute` with calendar.create binding
  - And: `invoke_capability` creates the calendar event
  - And: `submit_result(complete)` is called with evidence
  - And: No policy violations, no HIL gates triggered
- **Run:** `pytest tests/k1/concierge/actors/test_back_resolve_situation_live.py::test_back_calendar_create_happy_path -v`

### Issue 18.3 — Test: resolve_situation → blocked_by_policy → cannot_execute

- **File:** Same test file
- **Test:** `test_back_delete_protected_calendar_blocked`
  - Given: task dispatch for "Delete the family shared calendar"
  - When: Back handler processes the task
  - Then: `resolve_situation` returns `blocked_by_policy` (protected parent calendar)
  - And: Back calls `submit_result(cannot_execute, reason="blocked_by_policy: ...")`
  - And: No calendar was deleted
- **Run:** `pytest tests/k1/concierge/actors/test_back_resolve_situation_live.py::test_back_delete_protected_calendar_blocked -v`

### Issue 18.4 — Test: resolve_situation → needs_hil → submit suspended

- **File:** Same test file
- **Test:** `test_back_ambiguous_person_triggers_hil`
  - Given: task dispatch mentioning "schedule a meeting with Alex" (ambiguous — two Alexes in household)
  - When: Back handler processes the task
  - Then: `resolve_situation` returns `needs_disambiguation`
  - And: Back calls `submit_result(needs_human, questions=[...])` with disambiguation question
  - And: Task is suspended (not failed)
- **Run:** `pytest tests/k1/concierge/actors/test_back_resolve_situation_live.py::test_back_ambiguous_person_triggers_hil -v`

### Issue 18.5 — Test: resolve_situation → discover_capabilities fallback

- **File:** Same test file
- **Test:** `test_back_fallback_to_discover_when_resolve_returns_missing_capability`
  - Given: task dispatch for an operation that has no bound capability
  - When: `resolve_situation` returns `missing_capability`
  - Then: Back falls back to `discover_capabilities` for alternative search
  - And: If fallback also finds nothing, Back calls `submit_result(cannot_execute)`
- **Run:** `pytest tests/k1/concierge/actors/test_back_resolve_situation_live.py::test_back_fallback_to_discover_when_resolve_returns_missing_capability -v`

---

## Phase 2 Summary

| Epic | Issues | Files Created | Files Modified | Tests |
|------|--------|--------------|----------------|-------|
| 15 — Context Plumbing | 7 | 1 (test) | 4 (session.py, back_router.py, back.py, back_prompt.py) | GAP-028 (5 tests) |
| 16 — Tool Contract Migration | 5 | 1 (test) | 3 (schemas_back.py, back.py, back_prompt.py) | GAP-029 (5 tests) |
| 17 — Back Prompt Redesign | 3 | 1 (test) | 1 (back_prompt.py) | GAP-030 (5 tests) |
| 18 — Integration Gate | 5 | 1 (test) | 0 (test-only) | GAP-031 (5 tests) |
| **Total** | **20** | **4 new test files** | **~6 modified** | **~20 tests** |

**Phase 1 + Phase 1.1 + Phase 2 combined: 85 issues, 36 new files, ~17 modified, ~305 tests.**

---

## Discovery Checklist — What Each Epic MUST Research Before Implementation

### Epic 15 Discovery Items

- [ ] Does `ConciergeRuntime` store `_self_model`? If not, add `set_self_model()` method
- [ ] What is `TemporalHandle.get_context_for_actor("back")` API? Does it exist or need creation?
- [ ] What is `SpatialHandle.get_context_for_actor("back")` API? Does it exist or need creation?
- [ ] What is `SelfModelHandle.get_prompt_context()` API? Does it exist or need creation?
- [ ] Should context blocks be separate (`{temporal_context_block}`, `{spatial_context_block}`, `{selfmodel_context_block}`) or merged into one `{execution_context_block}`?
- [ ] Does `back_resume_handler()` also need temporal/spatial/selfmodel params?

### Epic 16 Discovery Items

- [ ] Read `ResolveSituationRequest` dataclass fully — which fields should be in the JSON Schema vs. auto-filled by Back dispatcher?
- [ ] How does Back's tool dispatcher reach Fabric? Is the Fabric instance accessible from `ToolDispatcher`?
- [ ] Does `_maybe_rebind_back_dispatcher()` need a new meta-tool registration path for `resolve_situation`?
- [ ] Are there concurrency concerns with Back calling `resolve_situation` while Front is simultaneously using Fabric?
- [ ] What does the `ResolutionEnvelope` dict look like when returned to Back's LLM? Is it too large? Does it need `disclosure_phase` control?

### Epic 17 Discovery Items

- [ ] Read full current `BACK_SYSTEM_PROMPT` (~200 lines) — map each section to KEEP/UPDATE/REPLACE
- [ ] What verdict names are stable vs. likely to change? Don't over-fit prompt to specific verdict strings
- [ ] How does the new prompt interact with `BackExecutionWorkItem` tracking? Does Back need to track which binding it's executing?
- [ ] What's the model context limit? Verify prompt + envelope + tools fit within budget

### Epic 18 Discovery Items — ALL RESOLVED (2026-06-09)

- [x] What's the minimal kernel subset? **Pattern A (direct handler) for unit tests, Pattern B (KernelService test_mode) for full integration.**
- [x] Real LLM or scripted? **Scripted via `TestModelHubBridge` (Pattern A, proven in `test_back_handler_profile_wiring.py`).**
- [x] Test ordering dependencies? **Calendar connector registered via `register_definition_to_store()` in fixture setup.**
- [x] Cleanup? **In-memory SQLite stores (`:memory:`) — no filesystem cleanup needed.**

---

## Phase 2 Final Coherence Sweep

### Port/Adapter Compliance

| Check | Result |
|-------|--------|
| Epic 15: Handle params through consumer→handler chain | ✅ `TemporalHandle`, `SpatialHandle`, `SelfModelHandle` — port-compatible facades |
| Epic 16: `FabricDispatchAdapter.resolve_situation()` | 🔴→✅ **FIXED** — calls public `self._fabric.resolve_situation(request)`, not private `_handle_resolve_situation` |
| Epic 16: `execute_resolve_situation()` handler | ✅ Uses `ctx.dispatch.resolve_situation()` — protocol path |
| Epic 17: Conversation injection helpers | ✅ Duck-typing via `getattr()` — no `TypedHistoryEntry` import needed |
| Epic 18: Test fixtures | ✅ Reuses Patterns A/B/C — no new kernel boot paths |
| All: Zero new direct imports from `k1.fabric.fabric` | ✅ |
| All: Zero new direct imports from `k1.spatial.service.*` | ✅ |
| All: Zero new direct imports from `k1.selfmodel.*` internals | ✅ |
| All: Zero new direct imports from `k1.grounding.service.*` | ✅ |

### Kernel Feature Flags Required for Phase 2

| Flag | Default | Required? | Why |
|------|---------|-----------|-----|
| `enable_temporal` | `True` | ✅ Required | Epic 15 temporal context |
| `enable_spatial` | `True` | ✅ Required | Epic 15 spatial context |
| `enable_grounding` | `True` | ✅ Required | Existing — already used by Back |
| `enable_self_model` | `False` | ⚠️ Optional | Epic 15 selfmodel context (gracefully degrades if False) |
| `enable_fabric_stores` | `True` | ✅ Required | Epic 16 resolve_situation tool |
| `enable_family_tools` | `True` | ✅ Required | Calendar connector for integration tests |
| `enable_hil_service` | `True` | ✅ Required | HIL gate testing in Epic 18 |
| `test_mode` | `False` | ✅ Required (tests only) | Uses `StubProviderPlugin` for LLM calls |

### Variable Count Final: 16 prompt variables

| # | Variable | Epic | Data Source |
|---|----------|------|------------|
| 1-6 | `{task_json}`, `{beliefs_summary}`, `{task_state_summary}`, `{artifacts_summary}`, `{safety_band}`, `{persona_prefs}` | Existing | SS snapshot |
| 7 | `{max_tool_calls}` | Existing | Tier config |
| 8 | `{available_tools_note}` | Epic 16 | Generated from tier |
| 9 | `{temporal_context_block}` | Epic 15 | `TemporalHandle.get_projection("back")` |
| 10 | `{spatial_context_block}` | Epic 15 | `SpatialHandle.get_projection("back")` |
| 11 | `{selfmodel_context_block}` | Epic 15 | `SelfModelHandle.render_capsule()` |
| 12 | `{execution_grounding_block}` | Existing | Grounding handle |
| 13 | `{scoreboard_summary}` | Epic 17 | `snapshot["referents"]` |
| 14 | `{triggering_utterance}` | Epic 17 | `snapshot["history_entries"]` last `"user"` |
| 15 | `{conversation_prefix}` | Epic 17 | `snapshot["history_entries"]` last `"final"` |
| 16 | `{recent_history}` | Epic 17 | `snapshot["history_entries"]` last N entries |

---

# Phase 2.5 — Front LLM Read Surface (`lookup`)

> **Milestone:** GATE-P2.5 — Front LLM can call `lookup()` to dynamically discover and read from connected family data sources.
> **Predecessor:** Phase 2 (GATE-P2 must pass first)
> **Successor:** Phase 3 — Front LLM prompt redesign + dispatch redesign (TBD)
> **Scope:** Epics 19–21. New `lookup` tool bridging GPS→LPS dynamic discovery, a `snapshot_types` pipeline through the store layer, and a `LookupAdapter` wired into the kernel.
> **Design source:** `k1/docs/future_work/front_llm_read_k1surface.md`

---

## Architecture Context: What `lookup` Enables

**Today (legacy model):**

```
Front LLM sees user message → DynamicPromptBuilder builds a fixed prompt from
  SessionState sections → Front responds conversationally → No read-only data
  access beyond what was pre-loaded into grounding context
```

**Problem:** Front can't dynamically discover "what data is available right now" — it only sees pre-loaded SS snapshots. A user asking "what's on the calendar today?" gets whatever the grounding projection loaded at session start, not live data. Front has NO read tool to query family data sources.

**Target (Phase 2.5):**

```
Front LLM sees user message → calls lookup() with a natural language query
  → LookupAdapter resolves GPS → LPS dynamic discovery → returns typed
  snapshot from matching connectors → Front LLM reads snapshot data and
  responds conversationally
```

- `lookup` is a READ-ONLY tool — no mutations, no side effects
- Domain-agnostic: same tool works for calendars, tasks, chores, shopping, reminders
- Dynamic GPS→LPS discovery: `lookup` finds connectors via `snapshot_types` field in GPS, then reads data via LPS (connected resources)
- `snapshot_types` is the bridge: connectors declare which snapshot views they participate in (`daily_snapshot`, `weekly_overview`, `contextual_probe`)

---

## Key File Touch Points — Phase 2.5 At a Glance

| File | Epic 19 | Epic 20 | Epic 21 | What Changes |
|------|---------|---------|---------|-------------|
| `k1/tools/family/definition.py` | ✅ | — | — | `ToolDefinition.snapshot_types` field added (already designed in Epic 9.1) |
| `k1/fabric/stores/global_projection_store.py` | ✅ | — | — | `connectors` table gains `snapshot_types_json` column; `ConnectorRecord` gains `snapshot_types` field; new `list_connectors_by_snapshot_type()` query method |
| `k1/fabric/manifest_translator.py` | ✅ | — | — | `register_definition_to_store()` writes `snapshot_types` to connector record |
| `k1/concierge/adapters/lookup.py` | — | ✅ | — | **NEW** `LookupAdapter` class with `build_lookup_fn()` closure |
| `k1/concierge/ports.py` | — | ✅ | — | `ILookupPort` protocol added; `IDispatchPort` unchanged |
| `k1/concierge/factory.py` | — | ✅ | — | `PortBundle` gains `lookup: ILookupPort` field |
| `k1/concierge/tools/context.py` | — | ✅ | — | `ToolContext` gains `lookup_fn: Callable | None` attribute |
| `k1/kernel/service.py` | — | ✅ | — | P4: `LookupAdapter` created + wired into `PortBundle` |
| `k1/fabric/stores/local_projection_store.py` | — | ✅ | — | `list_connected_resources()` extended with `snapshot_type` filter (verify existing API) |
| `k1/concierge/tools/schemas_front.py` | — | — | ✅ | `LOOKUP_SCHEMA` defined; added to `_FRONT_SIMPLE` allowlist |
| `k1/concierge/tools/implementations.py` | — | — | ✅ | `execute_lookup` handler registered via `@_register("lookup")` |
| `tests/k1/concierge/tools/test_lookup.py` | — | — | ✅ | **NEW** integration test for `lookup` tool |
| 5 connector definition files (calendar, tasks, reminders, chores, shopping) | ✅ | — | — | `snapshot_types` populated (already designed in Epics 9-13) |

---

## Epic 19: Store Layer — `snapshot_types` Pipeline

**Goal:** Build the end-to-end `snapshot_types` pipeline: `ToolDefinition.snapshot_types` → `ConnectorRecord.snapshot_types` → `connectors` table column → `list_connectors_by_snapshot_type()` query → `lookup` tool discovers participating connectors.

**Why:** `snapshot_types` is the bridge between declarative connector metadata ("I participate in daily snapshots") and runtime dynamic discovery ("which connectors should I read for a daily overview?"). Without this pipeline, `lookup` can't dynamically discover which connectors to query.

**Design derivation:** `snapshot_types` was designed in Epic 9.1 as an `Optional[list[str]]` field on `ToolDefinition`. It has been populated in Epics 9.2, 10.2, 11.2, 12.2, 13.2 for all 5 family connectors. The connector values are:

| Connector | `snapshot_types` |
|-----------|-----------------|
| `family.calendar` | `["daily_snapshot", "weekly_overview"]` |
| `family.tasks` | `["daily_snapshot", "weekly_overview"]` |
| `family.reminders` | `["daily_snapshot", "weekly_overview"]` |
| `family.chores` | `["daily_snapshot", "weekly_overview"]` |
| `family.shopping` | `["daily_snapshot"]` |

**Codebase status (verified 2026-06-09):** `snapshot_types` is **100% design-only** — zero matches in any `k1/**/*.py` file. The `connectors` table has NO `snapshot_types_json` column. `ConnectorRecord` has NO `snapshot_types` field. The full pipeline from `ToolDefinition` → store → query needs to be built from scratch.

---

### Issue 19.1 — Add `snapshot_types` Field to ConnectorRecord

- **File:** `k1/fabric/stores/global_projection_store.py` — `ConnectorRecord` dataclass
- **What:** Add `snapshot_types: list[str] = field(default_factory=list)` to `ConnectorRecord`.
- **Default:** `[]` (empty list) — connectors that don't participate in any snapshot views.
- **Coherence:** Must match `ToolDefinition.snapshot_types: Optional[list[str]]` (Epic 9.1). The manifest translator (Issue 19.5) handles the `Optional` → `list` coercion.

### Issue 19.2 — Add `snapshot_types_json` Column to `connectors` Table

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()` method
- **What:** Add `snapshot_types_json TEXT NOT NULL DEFAULT '[]'` column to the `connectors` CREATE TABLE statement.
- **Migration:** Since this is Phase 2.5 (post-GATE-P2), use `ALTER TABLE connectors ADD COLUMN snapshot_types_json TEXT NOT NULL DEFAULT '[]'` in a migration block if the table already exists. For fresh installs, include in CREATE TABLE.
- **Serialization:** JSON array of strings, e.g. `'["daily_snapshot", "weekly_overview"]'`.

### Issue 19.3 — Update `upsert_connector()` to Write `snapshot_types`

- **File:** `k1/fabric/stores/global_projection_store.py` — `upsert_connector()` method
- **What:** Add `snapshot_types_json` to the INSERT/UPDATE SQL. Serialize `connector.snapshot_types` to JSON via `json.dumps(sort_keys=True)`.
- **Coherence:** Existing `resource_kinds_json` column uses the same pattern — follow it.

### Issue 19.4 — Update `get_connector()` / `list_connectors()` to Read `snapshot_types`

- **File:** `k1/fabric/stores/global_projection_store.py` — `get_connector()`, `list_connectors()`
- **What:** Deserialize `snapshot_types_json` → `list[str]` when constructing `ConnectorRecord` from a DB row. Use `json.loads()` with default `[]`.

### Issue 19.5 — Update `register_definition_to_store()` to Populate `snapshot_types`

- **File:** `k1/fabric/manifest_translator.py` — `register_definition_to_store()`
- **What:** When building `ConnectorRecord` from `ToolDefinition`, populate `snapshot_types` from `definition.snapshot_types` (coerce `None` → `[]`).
- **One-line change:** `snapshot_types=definition.snapshot_types or []`

### Issue 19.6 — Add `list_connectors_by_snapshot_type()` Query Method

- **File:** `k1/fabric/stores/global_projection_store.py`
- **What:** New public method:

  ```python
  def list_connectors_by_snapshot_type(self, snapshot_type: str) -> list[ConnectorRecord]:
      """Return all connectors that participate in the given snapshot type.

      Uses JSON_EACH or LIKE pattern matching on snapshot_types_json.
      Returns empty list if no connectors match.
      """
  ```

- **Implementation options (TBD during code discovery):**
  - **Option A:** SQLite `json_each()` — `SELECT * FROM connectors WHERE EXISTS (SELECT 1 FROM json_each(snapshot_types_json) WHERE value = ?)`
  - **Option B:** LIKE pattern — `WHERE snapshot_types_json LIKE '%"daily_snapshot"%'`
  - **Recommendation A:** `json_each` is correct; LIKE has false positives on overlapping names.
- **Also add:** `list_snapshot_types() -> list[str]` — returns distinct snapshot types across all connectors. Useful for `lookup` to know what snapshot types are available.

### Issue 19.7 — Verify `local_projection_store.list_connected_resources()` Readiness

- **File:** `k1/fabric/stores/local_projection_store.py`
- **What:** Verify the existing `list_connected_resources()` method can be filtered by `resource_kind` and `actor_id`. This is what `lookup` uses to find matching connected resources after discovering connectors via GPS.
- **Discovery needed:** Does `list_connected_resources()` support `resource_kind` filtering? If not, add it. The existing signature is `list_connected_resources(actor_id, *, resource_kind=None, status="active")` per Epic 1.5 — verify this matches the actual implementation.

### Issue 19.8 — Tests for `snapshot_types` Pipeline

- **GAP-P2.5-001:** `tests/k1/fabric/stores/test_snapshot_types.py`
  - `TestConnectorRecordHasSnapshotTypes` — `ConnectorRecord.snapshot_types` field exists, defaults to `[]`
  - `TestUpsertAndReadSnapshotTypes` — write connector with `snapshot_types=["daily_snapshot"]`, read back, verify
  - `TestSnapshotTypesEmptyByDefault` — connector without snapshot_types → `[]` on read
  - `TestListConnectorsBySnapshotType` — 3 connectors: 2 with "daily_snapshot", 1 with "weekly_overview" → `list_connectors_by_snapshot_type("daily_snapshot")` returns 2
  - `TestListConnectorsBySnapshotTypeNoMatch` — unknown snapshot type → empty list
  - `TestListSnapshotTypes` — returns deduplicated list across all connectors
  - `TestManifestTranslatorPopulatesSnapshotTypes` — `register_definition_to_store()` with a definition that has `snapshot_types=["daily_snapshot"]` → store has correct JSON
  - `TestManifestTranslatorCoercesNoneToEmpty` — `snapshot_types=None` → stored as `[]`
- **Run:** `pytest tests/k1/fabric/stores/test_snapshot_types.py -v`

---

## Epic 20: Adapter + Kernel Wiring — `LookupAdapter`

**Goal:** Build `LookupAdapter` that implements dynamic GPS→LPS discovery. Wire it into `PortBundle`, `ToolContext`, and kernel P4 lifecycle.

**Design:** `lookup` is domain-agnostic. The Front LLM provides a natural language query + optional snapshot_type hint. The adapter:

1. Queries GPS for connectors with matching `snapshot_types`
2. For each matching connector, queries LPS for connected resources
3. Reads fresh data from each connected resource via the connector's native adapter
4. Returns a typed `LookupResult` with per-connector snapshots

---

### Issue 20.1 — Define `LookupResult` Dataclass

- **File:** `k1/concierge/adapters/lookup.py` (NEW)
- **What:** Typed return dataclass for the lookup operation:

  ```python
  @dataclass(frozen=True)
  class ConnectorSnapshot:
      """Snapshot data from one connector for a lookup query."""
      connector_id: str                    # "family.calendar"
      resource_kind: str                   # "calendar_event"
      snapshot_type: str                   # "daily_snapshot"
      data: list[dict[str, Any]]           # raw rows from the connector
      freshness: str                       # 'fresh' | 'stale' | 'unknown'
      error: str | None = None             # per-connector error message

  @dataclass(frozen=True)
  class LookupResult:
      """Complete result of a lookup() call."""
      lookup_id: str
      query: str                           # original natural language query
      snapshot_type: str | None            # resolved snapshot type
      connectors_queried: int              # how many connectors were attempted
      snapshots: list[ConnectorSnapshot]   # per-connector results
      omissions: list[str]                 # connectors found but skipped (stale, error, permission)
      diagnostics: list[str]               # human-readable diagnostics
      created_at: str
  ```

### Issue 20.2 — Build `build_lookup_fn()` Closure

- **File:** `k1/concierge/adapters/lookup.py`
- **What:** `build_lookup_fn(global_store, local_store, native_dispatch) -> Callable` that returns the actual `lookup()` async function. This follows the same closure pattern used by `recall_memory` (a closure is built at wiring time and injected into `ToolContext`).
- **Implementation sketch:**

  ```python
  def build_lookup_fn(
      global_store: GlobalProjectionStore,
      local_store: LocalProjectionStore,
      native_dispatch: Any,  # NativeToolProvider or equivalent
  ):
      async def lookup(
          query: str,
          *,
          actor_id: str,
          space_id: str,
          snapshot_type: str | None = None,
          max_connectors: int = 5,
      ) -> LookupResult:
          """Domain-agnostic dynamic data discovery.

          1. Discover: query GPS for connectors matching snapshot_type.
          2. Resolve: query LPS for connected resources matching connectors.
          3. Read: dispatch read to each connected resource's native adapter.
          4. Return: LookupResult with per-connector snapshots.
          """
          ...

      return lookup
  ```

- **Discovery needed:** The exact call pattern for dispatching a read to a native adapter. Back uses `ctx.dispatch.dispatch_direct(CapabilityRequest(...))` for invoke. For `lookup`, we need a read-only path — possibly `ctx.dispatch.discover_capabilities()` or a new `read_resource()` method on native providers.

### Issue 20.3 — Create `LookupAdapter` Class

- **File:** `k1/concierge/adapters/lookup.py`
- **What:** `LookupAdapter` wraps `build_lookup_fn()` and implements the `ILookupPort` protocol:

  ```python
  class LookupAdapter:
      def __init__(self, lookup_fn: Callable): ...
      async def lookup(self, query: str, *, actor_id: str, space_id: str,
                       snapshot_type: str | None = None) -> LookupResult: ...
  ```

### Issue 20.4 — Add `ILookupPort` Protocol to `ports.py`

- **File:** `k1/concierge/ports.py`
- **What:** New protocol alongside existing `IDispatchPort`:

  ```python
  class ILookupPort(Protocol):
      async def lookup(self, query: str, *, actor_id: str, space_id: str,
                       snapshot_type: str | None = None) -> LookupResult: ...
  ```

### Issue 20.5 — Add `lookup` to `PortBundle` + Wire in `factory.py`

- **File:** `k1/concierge/factory.py` — `PortBundle` dataclass
- **What:** Add `lookup: ILookupPort | None = None` field. Wire `LookupAdapter` into `_build_port_bundle()`:

  ```python
  # In _build_port_bundle(), after temporal/spatial/grounding wiring:
  lookup_fn = build_lookup_fn(
      global_store=runtime._global_projection_store,
      local_store=session_local_store,
      native_dispatch=...,  # TBD during discovery
  )
  port_bundle.lookup = LookupAdapter(lookup_fn)
  ```

- **Discovery needed:** Where does `PortBundle` get `global_projection_store` and `local_projection_store`? These may need to be added to `ConciergeRuntime` or passed through the factory chain.

### Issue 20.6 — Add `lookup_fn` to `ToolContext`

- **File:** `k1/concierge/tools/context.py` — `ToolContext` dataclass
- **What:** Add `lookup_fn: Callable | None = None` attribute. This is set by the concierge factory when creating the tool context for Front's dispatcher.
- **Follow pattern:** `recall_fn` at `context.py` is the existing example — `lookup_fn` follows the same injection pattern.

### Issue 20.7 — Kernel P4 Wiring for `LookupAdapter`

- **File:** `k1/kernel/service.py` — `_create_session_tier2()` per-session P4
- **What:** After creating `ConciergeRuntime` and wiring `PortBundle`, create `LookupAdapter` and attach it:

  ```python
  # In P4, after concierge is created and port_bundle is assembled:
  from k1.concierge.adapters.lookup import build_lookup_fn, LookupAdapter

  lookup_fn = build_lookup_fn(
      global_store=self._global_projection_store,
      local_store=session_local_store,
      native_dispatch=...,  # TBD
  )
  port_bundle.lookup = LookupAdapter(lookup_fn)
  front_ctx.lookup_fn = lookup_fn  # inject into Front's ToolContext
  ```

- **Discovery needed:** The `native_dispatch` parameter needs the same provider dispatch that Back uses for `invoke_capability`. Find the correct reference in the kernel's P4 wiring.

### Issue 20.8 — Tests for LookupAdapter

- **GAP-P2.5-002:** `tests/k1/concierge/adapters/test_lookup_adapter.py`
  - `TestLookupResultShape` — dataclass fields correct
  - `TestBuildLookupFnReturnsCallable` — `build_lookup_fn(...)` returns async callable
  - `TestLookupDiscoversConnectors` — GPS has 2 connectors with "daily_snapshot" → `lookup(snapshot_type="daily_snapshot")` discovers 2
  - `TestLookupResolvesConnectedResources` — LPS has connected resources matching discovered connectors → data read
  - `TestLookupSkipsStaleResources` — stale connected resource → omitted with reason
  - `TestLookupNoMatchingConnectors` — unknown snapshot_type → empty snapshots, diagnostics explain
  - `TestLookupMaxConnectorsLimit` — 10 connectors match but max_connectors=3 → only 3 returned
- **Run:** `pytest tests/k1/concierge/adapters/test_lookup_adapter.py -v`

---

## Epic 21: Tool Surface — `lookup` Tool for Front LLM

**Goal:** Register `lookup` as a Front-callable tool. Front LLM sees it in its tool list, can call it with natural language queries, and receives structured `LookupResult` data to incorporate into its conversational response.

---

### Issue 21.1 — Define `LOOKUP_SCHEMA`

- **File:** `k1/concierge/tools/schemas_front.py` — after existing `RECALL_MEMORY_SCHEMA` (~line 355)
- **What:** Define `LOOKUP_SCHEMA` as a new `ToolSchema`:

  ```python
  LOOKUP_SCHEMA = ToolSchema(
      name="lookup",
      description=(
          "Read current data from connected family resources. "
          "Use this to answer questions like 'what's on the calendar today?', "
          "'what chores are due?', 'what's on the shopping list?'. "
          "You provide a natural language query and optional snapshot_type hint. "
          "Returns a LookupResult with per-connector snapshot data. "
          "This is READ-ONLY — no data is modified."
      ),
      parameters={
          "type": "object",
          "properties": {
              "query": {
                  "type": "string",
                  "description": "Natural language description of what data to look up. E.g. 'today's calendar events', 'active chores', 'shopping list'"
              },
              "snapshot_type": {
                  "type": "string",
                  "enum": ["daily_snapshot", "weekly_overview", "contextual_probe"],
                  "description": "Optional hint for which snapshot view to use. Omit to auto-detect from the query."
              },
              "max_results": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 20,
                  "description": "Maximum number of results per connector. Default: 10."
              },
          },
          "required": ["query"]
      },
      returns={"type": "object", "description": "LookupResult with snapshots array, each containing connector_id, resource_kind, data rows, freshness"},
      category="read",
      side_effects=False,
      actor="front",
  )
  ```

- **Add to `FRONT_TOOL_SCHEMAS`** list (same file):

  ```python
  FRONT_TOOL_SCHEMAS: list[ToolSchema] = [
      ...,
      LOOKUP_SCHEMA,           # NEW
  ]
  ```

### Issue 21.2 — Add `lookup` to Front Tool Allowlist

- **File:** `k1/concierge/tools/schemas_front.py` — `_FRONT_SIMPLE` list
- **What:** Add `"lookup"` to the list of Front tools available in the simple/LOW tier:

  ```python
  _FRONT_SIMPLE: list[str] = [
      "recall_memory",
      "lookup",               # ← NEW
      ...
  ]
  ```

- **Front LLM always has `lookup` available** — it's a read-only tool with no side effects.

### Issue 21.3 — Register `execute_lookup` Handler

- **File:** `k1/concierge/tools/implementations.py` — new handler
- **What:** Register `@_register("lookup")` handler:

  ```python
  @_register("lookup")
  async def execute_lookup(args: dict, ctx: ToolContext) -> ToolResult:
      """Read current data from connected family resources.

      Domain-agnostic: works for calendars, tasks, chores, shopping,
      reminders — any connector that declares snapshot_types.
      """
      try:
          if not hasattr(ctx, "lookup_fn") or ctx.lookup_fn is None:
              return ToolResult(
                  status="error",
                  data={"lookup_id": "", "snapshots": [],
                        "diagnostics": ["lookup_fn not wired — Phase 2.5 stores not available"]}
              )

          query = str(args.get("query", ""))
          if not query.strip():
              return ToolResult(status="error", data={"diagnostics": ["query is required"]})

          snapshot_type = args.get("snapshot_type")  # None = auto-detect
          max_results = int(args.get("max_results", 10))

          result = await ctx.lookup_fn(
              query=query,
              actor_id=str(getattr(ctx, "active_principal_id", "") or ""),
              space_id=str(getattr(ctx, "active_space_id", "") or "family:default"),
              snapshot_type=snapshot_type,
              max_connectors=max_results,
          )
          return ToolResult(status="ok", data=asdict(result))
      except Exception as exc:
          return ToolResult(status="error", data={"diagnostics": [str(exc)]})
  ```

### Issue 21.4 — Integration Test: `lookup` End-to-End

- **File:** `tests/k1/concierge/tools/test_lookup.py` (NEW)
- **GAP-P2.5-003:**
  - `TestLookupSchemaValid` — schema parses with correct fields
  - `TestLookupInFrontSimpleAllowlist` — appears in `_FRONT_SIMPLE`
  - `TestLookupHandlerRegistered` — `TOOL_REGISTRY["lookup"]` exists
  - `TestLookupCalendarDailySnapshot` — `lookup(query="today's events", snapshot_type="daily_snapshot")` → returns calendar data
  - `TestLookupShoppingList` — `lookup(query="shopping list")` → returns shopping items from `family.shopping`
  - `TestLookupAutoDetectsSnapshotType` — `lookup(query="what chores are due")` without explicit snapshot_type → auto-detects "daily_snapshot" from query context
  - `TestLookupNoMatchingConnectors` — unknown domain → empty snapshots with diagnostics
  - `TestLookupUnwiredReturnsError` — `ctx.lookup_fn` is None → error ToolResult
  - `TestLookupIsReadOnly` — calling `lookup` does not modify any data (verify with second call returning same results)
- **Run:** `pytest tests/k1/concierge/tools/test_lookup.py -v`

---

## Phase 2.5 Summary

| Epic | Issues | Files Created | Files Modified | Tests |
|------|--------|--------------|----------------|-------|
| 19 — Store Layer | 8 | 1 (test) | 2 (global_projection_store.py, manifest_translator.py) + 5 connector defs (already done in Epics 9-13) | GAP-P2.5-001 (8 tests) |
| 20 — Adapter + Kernel Wiring | 8 | 1 (lookup.py) + 1 (test) | 3 (ports.py, factory.py, context.py, service.py) | GAP-P2.5-002 (7 tests) |
| 21 — Tool Surface | 4 | 1 (test) | 2 (schemas_front.py, implementations.py) | GAP-P2.5-003 (9 tests) |
| **Total** | **20** | **4 new files** | **~7 modified** | **~24 tests** |

**Phase 1 + 1.1 + 2 + 2.5 combined: 105 issues, 40 new files, ~24 modified, ~329 tests.**

---

## Phase 2.5 Discovery Checklist — What Each Epic MUST Research Before Implementation

### Epic 19 Discovery Items

- [ ] Verify `ConnectorRecord` current field list — confirm `snapshot_types` field doesn't already exist under a different name
- [ ] Verify `connectors` table current column list — confirm `snapshot_types_json` column doesn't already exist
- [ ] Check SQLite version for `json_each()` support (requires SQLite ≥ 3.38.0; check if any constraints)
- [ ] Verify `register_definition_to_store()` current implementation — confirm exact line where `ConnectorRecord` is constructed
- [ ] Verify 5 connector definition files (calendar/tasks/reminders/chores/shopping) — confirm `snapshot_types` field is populated as designed in Epics 9-13
- [ ] Check if `list_connected_resources()` in LPS supports `resource_kind` filter as designed in Epic 1.5

### Epic 20 Discovery Items

- [ ] How does `lookup` dispatch a read to a native adapter? Explore existing `NativeToolProvider` read path vs. `invoke_capability` path
- [ ] Where does `PortBundle` / `ConciergeRuntime` get `global_projection_store` and `local_projection_store` references?
- [ ] What is the exact `native_dispatch` reference in the kernel P4 wiring? Can we reuse the same reference Back uses for `invoke_capability`?
- [ ] Does `ToolContext` already have a `lookup_fn`-like pattern? Verify `recall_fn` injection pattern as template
- [ ] Should `lookup` go through `ILookupPort` protocol (new, separate from `IDispatchPort`) or be added to `IDispatchPort`? **Recommendation:** Separate `ILookupPort` — lookup is a read-only tool for Front, distinct from Back's dispatch path.

### Epic 21 Discovery Items

- [ ] Verify `FRONT_TOOL_SCHEMAS` current list — confirm where `LOOKUP_SCHEMA` should be added
- [ ] Verify `_FRONT_SIMPLE` current list — confirm all entries and where `"lookup"` fits
- [ ] Verify `ToolContext` has `active_principal_id`, `active_space_id` attributes — confirm names for auto-fill
- [ ] Check if Front's `react_loop` / tool dispatcher needs any change to support the new `lookup` category tool
- [ ] Determine: should `lookup` be available to Front ONLY, or also to Back? **Recommendation:** Front-only for Phase 2.5. Back has `resolve_situation` which provides more structured access.

---

## Phase 2.5 Coherence Sweep

### Port/Adapter Compliance

| Check | Result |
|-------|--------|
| Epic 19: `GlobalProjectionStore` public query method | ✅ `list_connectors_by_snapshot_type()` — new public method |
| Epic 19: `ManifestTranslator` field population | ✅ `register_definition_to_store()` reads `ToolDefinition.snapshot_types` |
| Epic 20: `LookupAdapter` → `ILookupPort` protocol | ✅ New protocol, adapter implements it |
| Epic 20: `PortBundle.lookup` → `ToolContext.lookup_fn` | ✅ Follows existing `recall_fn` injection pattern |
| Epic 21: `execute_lookup` → `ctx.lookup_fn` | ✅ Protocol path — no direct Fabric import |
| All: Zero new direct imports from `k1.fabric.fabric` | ✅ |
| All: Zero new direct imports from `k1.spatial.*` | ✅ |
| All: Zero new direct imports from `k1.selfmodel.*` | ✅ |

### Kernel Feature Flags Required for Phase 2.5

| Flag | Default | Required? | Why |
|------|---------|-----------|-----|
| `enable_fabric_stores` | `True` | ✅ Required | Epic 19 GPS + LPS queries |
| `enable_front_tools` | `True` | ✅ Required | Epic 21 `lookup` tool registration |
| `enable_family_tools` | `True` | ✅ Required | Connectors must have `snapshot_types` populated |

### Data Flow: `lookup` End-to-End

```
Front LLM calls lookup(query="today's events")
  → execute_lookup(args, ctx)                    [implementations.py]
    → ctx.lookup_fn(query, actor_id, space_id)   [ToolContext → closure]
      → LookupAdapter.lookup()                   [adapters/lookup.py]
        → GPS.list_connectors_by_snapshot_type("daily_snapshot")
          → returns [family.calendar, family.tasks, family.reminders,
                     family.chores, family.shopping]
        → For each connector:
            LPS.list_connected_resources(actor_id, resource_kind=...)
              → returns connected resource IDs
            native_dispatch.read_resource(resource_id, ...)
              → returns current data rows
        → LookupResult {
            snapshots: [
              ConnectorSnapshot(connector_id="family.calendar", data=[...]),
              ConnectorSnapshot(connector_id="family.tasks", data=[...]),
              ...
            ]
          }
  → ToolResult(status="ok", data=LookupResult)
    → Front LLM reads snapshot data, responds conversationally
```
