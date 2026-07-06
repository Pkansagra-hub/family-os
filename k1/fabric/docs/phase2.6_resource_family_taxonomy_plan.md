# Phase 2.6 — Domain & Resource Family Taxonomy

> **Milestone:** GATE-P2.6 — Every connector maps to a governed domain and resource family. The resolver uses FTS5 full-text search as a safety net when structured resolution returns null. Back's prompt renders live taxonomy from GPS — no hardcoded lists.
> **Predecessor:** Phase 2 Epics 15-17 (Back prompt redesign, context plumbing, tool contract migration)
> **Successor:** Phase 2.5 — Front LLM Read Surface (`lookup`)
> **Scope:** Epics 22–27. Touches GPS schema (6 new tables), all 6 family tool definitions, resolver (graph lookup + FTS5 fallback + self-healing ontology), Back prompt (domain-scoped live rendering from GPS), and documentation.

---

## Architecture Context

```
┌─────────────────────────────────────────────────────────────┐
│                 TAXONOMY (FamilyOS-Governed)                 │
│                                                             │
│  domains               domain_resource_families             │
│  ┌──────────────┐      ┌────────────────────────┐          │
│  │ family       │─────→│ family.event           │          │
│  │ finance      │      │ family.task            │          │
│  │ health       │      │ family.chore           │          │
│  │ education    │      │ family.item            │          │
│  │ home         │      │ family.recipe          │          │
│  │ transport    │      │ finance.account        │          │
│  │ food         │      │ finance.transaction    │          │
│  │ fitness      │      │ health.prescription    │          │
│  │ ...          │      │ ...                    │          │
│  └──────────────┘      └───────────┬────────────┘          │
│                                    │                        │
│               resource_families    │                        │
│               ┌──────────────┐     │                        │
│               │ event        │←────┘                        │
│               │ task         │                              │
│               │ account      │                              │
│               │ prescription │                              │
│               │ recipe       │                              │
│               │ ...          │                              │
│               └──────────────┘                              │
│                                                             │
│   connector_resource_families (connector dev declares)      │
│   ┌──────────────────────────────────────────┐             │
│   │ finance.chase → [account, transaction]   │             │
│   │ health.fitbit → [metric, workout]        │             │
│   │ family.calendar → [event]                │             │
│   │ family.shopping → [item]                 │             │
│   └──────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

---

## Problem Statement

| Problem | Evidence |
|---------|----------|
| **No domain table — inferred from connector_id prefix** | `connector_id LIKE 'family.%'` is the only domain filter. No FK. No validation. No reference data. |
| **Resource families are a free-for-all** | 47 unique `resource_kind` values for ~52 capabilities. Phase 1.1 catalog loader injected 50 synthetic connectors with random names: `animal`, `bug`, `irrigation_schedule`, `equipment_log`, `harvest_plan`, `imaging_order`. |
| **Same concept, different column names** | `capabilities.resource_kind` (nullable), `capability_type_index.resource_family`, `resource_kinds.kind_id` (dot notation) — three names for one concept. |
| **No domain→family mapping** | Which resource families belong to which domain? No table. Resolver can't narrow search by domain-scoped families. |
| **Resolver returns `can_execute` with empty bindings** | 13-step cascade falls through when `primary is None AND no all_bindings`. (Fixed in-session, step 11b.) |
| **CapabilityTypeResolver never uses FTS5** | `capabilities_fts` exists with BM25. Resolver does 4-step graph only. |
| **Back prompt tried to enumerate all resource families** | 47 values. Domain query was broken (no `domain` column). At 100K tools, impossible. |
| **Family tool definitions are internally inconsistent** | Tasks: `entity_type=task_item` vs `resource_kinds=["task"]`. Chores: `entity_type=chore_occurrence` vs `resource_kinds=["chore"]`. |

---

## The Contract

### Domain Is The First Cut

The `domains` table is the top-level taxonomy. Every connector, every capability, every resource family is scoped to a domain.

**FamilyOS controls:** `domains` table. New domains go through FamilyOS review.

**Connector developer:** Picks domain from approved list. Declares in `connector_id` as `{domain}.{name}`. FK constraint enforces it.

**Back sees:** "Currently active domains: family, finance, health, home." (5-16 values, stable.)

### Resource Family Is Domain-Scoped

A resource family says "what kind of real-world thing does this connector operate on?" It's NOT a connector implementation detail. Multiple connectors in the same domain can use the same family.

| Good (real-world concept) | Bad (connector implementation) |
|---------------------------|-------------------------------|
| `event` | `calendar_event` |
| `item` | `shopping_list_item` |
| `account` | `chase_checking_account` |
| `workout` | `fitbit_exercise_log` |
| `prescription` | `cvs_medication_refill` |

**FamilyOS controls:** `resource_families` table + `domain_resource_families` mapping. New families reviewed during connector admission.

**Connector developer:** Declares which families their connector manages. Picks from approved list for their domain. Proposes new ones if genuinely needed.

**Back sees:** "For family domain: event (appointments, meetings), task (to-dos, homework), chore (recurring duties), item (groceries, supplies), recipe (meals)." (5-12 per domain.)

**Same family, multiple domains:** `event` exists in `family`, `health`, `education`, `productivity`. Each mapping is independently approved.

---

## GPS Schema — Four New Tables

```sql
-- 1. DOMAIN TAXONOMY
CREATE TABLE IF NOT EXISTS domains (
    domain_id    TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    description  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. RESOURCE FAMILY TAXONOMY
CREATE TABLE IF NOT EXISTS resource_families (
    family_id    TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    description  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. DOMAIN ↔ RESOURCE FAMILY
CREATE TABLE IF NOT EXISTS domain_resource_families (
    domain_id    TEXT NOT NULL REFERENCES domains(domain_id),
    family_id    TEXT NOT NULL REFERENCES resource_families(family_id),
    PRIMARY KEY (domain_id, family_id)
);

-- 4. CONNECTOR ↔ RESOURCE FAMILY
CREATE TABLE IF NOT EXISTS connector_resource_families (
    connector_id TEXT NOT NULL REFERENCES connectors(connector_id),
    family_id    TEXT NOT NULL REFERENCES resource_families(family_id),
    is_primary   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (connector_id, family_id)
);
```

**Migration to existing tables:**

```sql
ALTER TABLE connectors ADD COLUMN domain_id TEXT NOT NULL DEFAULT ''
    REFERENCES domains(domain_id);
UPDATE connectors SET domain_id = substr(connector_id, 1, instr(connector_id, '.') - 1)
    WHERE domain_id = '' AND instr(connector_id, '.') > 0;

ALTER TABLE capabilities ADD COLUMN domain_id TEXT NOT NULL DEFAULT '';
ALTER TABLE capabilities ADD COLUMN family_id TEXT;
UPDATE capabilities SET
    domain_id = (SELECT c.domain_id FROM connectors c WHERE c.connector_id = capabilities.connector_id),
    family_id = capabilities.resource_kind;
-- DROP COLUMN resource_kind after verified;
```

---

## Seed Data

### Domains (16)

```
family           Family & Household      Parenting, chores, calendar, shopping, meal planning
finance          Banking & Finance       Accounts, transactions, budgets, investments, taxes
health           Health & Wellness       Medical records, prescriptions, fitness, nutrition
education        Education & Learning    Courses, assignments, grades, degrees
home             Smart Home & Living     Devices, appliances, security, energy
transport        Transport & Travel      Rides, deliveries, flights, hotels, vehicles
food             Food & Cooking          Recipes, meal planning, groceries, restaurants
fitness          Fitness & Activity      Workouts, tracking, goals, wearables
entertainment    Media & Entertainment   Streaming, gaming, events, subscriptions
productivity     Work & Productivity     Notes, documents, projects, calendars, email
communication    Messaging & Social      Chat, calls, social media, announcements
government       Government & Civic      Permits, benefits, taxes, voting
legal            Legal & Compliance      Contracts, documents, filings
utilities        Utilities & Services    Electricity, water, gas, internet, waste
agriculture      Agriculture & Farming   Crops, livestock, equipment, weather
automotive       Automotive & Vehicles   Cars, maintenance, registration, insurance
```

### Resource Families (55+)

**Cross-domain families** (shared across many domains): `event`, `task`, `reminder`, `item`, `record`, `contact`, `setting`, `metric`, `subscription`, `message`, `order`.

**Domain-specific families:** `chore`, `recipe`, `account`, `transaction`, `budget`, `investment`, `loan`, `insurance`, `tax`, `prescription`, `immunization`, `lab_order`, `vital`, `allergy`, `condition`, `course`, `assignment`, `grade`, `credential`, `device`, `energy`, `security`, `ride`, `delivery`, `flight`, `hotel`, `vehicle`, `workout`, `meal`, `playlist`, `game`, `permit`, `benefit`.

Full seed SQL in `RESOURCE_FAMILY_TAXONOMY.md` (Epic 26).

### Domain → Family Mapping (sampling)

```
family        → event, task, reminder, chore, item, recipe, contact, setting, meal, record, subscription, message
finance       → account, transaction, budget, investment, loan, insurance, tax, record, contact, metric, subscription
health        → prescription, immunization, lab_order, vital, allergy, condition, event, contact, record, metric, insurance
education     → course, assignment, grade, credential, event, task, record, contact, subscription
home          → device, energy, security, setting, subscription, record
transport     → ride, delivery, flight, hotel, vehicle, order, subscription, record
food          → recipe, item, meal, subscription, order
fitness       → workout, metric, device, subscription, event, record
entertainment → subscription, playlist, game, event, order, item
```

---

## What Happens To Existing `resource_kind` Values

| Old Value | New Family ID | Domain | Connector |
|-----------|-------------|--------|-----------|
| `calendar_event`, `appointment` | `event` | `family` | `family.calendar` |
| `task`, `task_item` | `task` | `family` | `family.tasks` |
| `reminder` | `reminder` | `family` | `family.reminders` |
| `chore`, `chore_occurrence` | `chore` | `family` | `family.chores` |
| `shopping_item` | `item` | `family` | `family.shopping` |
| *(none)* | `setting` | `family` | `family.family_settings` |

---

## Epics

---

## Epic 22: GPS Schema — Taxonomy Tables + Migration

**Goal:** Create 4 new taxonomy tables, add `domain_id` to `connectors` + `capabilities`, add `family_id` to `capabilities` (alongside existing `resource_kind` — no DROP during migration). Foundation — everything builds on this.

### Codebase Reality (Pre-Epic State)

| File:Line | What's There |
|-----------|-------------|
| `gps.py:178-191` | `connectors` — 13 columns. No `domain_id`. `connector_id` = `"family.calendar"` |
| `gps.py:203-225` | `capabilities` — 18 columns. `resource_kind TEXT` (nullable). No `domain_id`. No `family_id` |
| `gps.py:312-319` | `capability_type_index` — already has `domain` + `resource_family` columns ✓ |
| `gps.py:279-295` | `concept_resource_edges` + `resource_connector_edges` — already use `domain` + `resource_family` ✓ |
| `gps.py:231-236` | `capabilities_fts` — FTS5 on `capability_name, description, resource_kind, connector_id` |
| `gps.py:226-229` | `idx_capability_lookup` — on `(resource_kind, invocation_mode, effect, connector_id, record_type, safety_band_min)` |
| `manifest_admission.py:193` | Derives domain: `d.connector_id.split(".")[0]` |
| `manifest_translator.py:311` | Hardcodes `domain = "family"` |
| `builder.py:26-32` | `_cap_name(invocation_mode, domain_id, service_id, action)` — domain is 3rd segment |
| `registry.py:143` | `register_definition_to_store(svc.DEFINITION, gps)` — called per adapter during S8 bootstrap |
| `kernel/service.py:1941` | `GlobalProjectionStore(self._config.global_projection_db_path or ":memory:")` |
| `kernel/service.py:2358` | `_build_registry_hints` — extracts domain from `connector_id` prefix via `substr()` |
| `kernel/service.py:2958` | `PortBundle` construction — `registry_hints` wired at line 2969 |

---

### Issue 22.1 — Create `domains` Table + Seed

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()`, after line 176 (before existing `connectors` CREATE TABLE)
- **DDL:**

  ```sql
  CREATE TABLE IF NOT EXISTS domains (
      domain_id    TEXT PRIMARY KEY,
      label        TEXT NOT NULL,
      description  TEXT NOT NULL,
      created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```

- **Seed (16 rows):** `INSERT OR IGNORE` loop after CREATE TABLE. Same list as plan above — `family` through `automotive`.
- **No migration needed** — new table-only, no existing data.

### Issue 22.2 — Create `resource_families` Table + Seed

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()`, after `domains` block
- **DDL:**

  ```sql
  CREATE TABLE IF NOT EXISTS resource_families (
      family_id    TEXT PRIMARY KEY,
      label        TEXT NOT NULL,
      description  TEXT NOT NULL,
      created_at   TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```

- **Seed (55+ rows):** `INSERT OR IGNORE` loop. Cross-domain families (`event`, `task`, `reminder`, `item`, `record`, `contact`, `setting`, `metric`, `subscription`, `message`, `order`) + domain-specific families (`chore`, `recipe`, `account`, `transaction`, `budget`, …).

### Issue 22.3 — Create `domain_resource_families` Table + Seed

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()`
- **DDL:**

  ```sql
  CREATE TABLE IF NOT EXISTS domain_resource_families (
      domain_id    TEXT NOT NULL REFERENCES domains(domain_id),
      family_id    TEXT NOT NULL REFERENCES resource_families(family_id),
      PRIMARY KEY (domain_id, family_id)
  );
  ```

- **Seed (100+ mappings):** `INSERT OR IGNORE` loop. E.g., `("family","event")`, `("family","task")`, `("family","chore")`, `("finance","account")`, etc.

### Issue 22.4 — Create `connector_resource_families` Table

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()`
- **DDL:**

  ```sql
  CREATE TABLE IF NOT EXISTS connector_resource_families (
      connector_id TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
      family_id    TEXT NOT NULL REFERENCES resource_families(family_id),
      is_primary   INTEGER NOT NULL DEFAULT 1,
      PRIMARY KEY (connector_id, family_id)
  );
  ```

- **No seed data.** Populated at bootstrap by `register_definition_to_store()` → `manifest_translator.py` (see Issue 22.8).

### Issue 22.5 — Add `domain_id` to `connectors` Table

- **File:** `k1/fabric/stores/global_projection_store.py`

**Migration SQL** (in `_ensure_schema()`, after `connectors` CREATE TABLE):

```sql
ALTER TABLE connectors ADD COLUMN domain_id TEXT NOT NULL DEFAULT '';
```

**Populate from existing data:**

```sql
UPDATE connectors SET domain_id = substr(connector_id, 1, instr(connector_id, '.') - 1)
    WHERE domain_id = '' AND instr(connector_id, '.') > 0;
```

**Dataclass** (`ConnectorRecord`, line 25): Add field `domain_id: str = ""`.

**`upsert_connector()` (line 323):** Add `domain_id` to INSERT column list, VALUES tuple, and ON CONFLICT SET clause. Column count: 13 → 14.

**`_row_to_connector()` (line 1143):** Add `domain_id=row["domain_id"]`.

**`list_connectors()` (~line 500):** No change — `SELECT *` auto-picks up new column.

**`search_capabilities_by_domain()` (line 565):** This method currently uses `c.connector_id LIKE 'family.%'` as a domain filter hack. **Replace** with `c.domain_id = ?` parameterized query. Method signature gains `domain_id: str` param.

### Issue 22.6 — Add `domain_id` + `family_id` to `capabilities`, Keep `resource_kind`

> **CRITICAL:** SQLite has no `DROP COLUMN` in older versions. The `resource_kind` column stays — nullable, alongside new `family_id`. Both are populated during migration. `resource_kind` is deprecated, not dropped. A future cleanup Epic removes it.

- **File:** `k1/fabric/stores/global_projection_store.py`

**Migration SQL** (after `capabilities` CREATE TABLE):

```sql
ALTER TABLE capabilities ADD COLUMN domain_id TEXT NOT NULL DEFAULT '';
ALTER TABLE capabilities ADD COLUMN family_id TEXT;
```

**Populate from existing data:**

```sql
UPDATE capabilities SET
    domain_id = COALESCE(
        (SELECT c.domain_id FROM connectors c WHERE c.connector_id = capabilities.connector_id),
        ''
    ),
    family_id = resource_kind
WHERE domain_id = '';
```

**Dataclass** (`CapabilityRecord`, line 43): Add `domain_id: str = ""`, `family_id: str | None = None`. Keep `resource_kind: str | None = None` — all three fields coexist.

**`upsert_capability()` (line 379):** Add `domain_id`, `family_id` to INSERT columns. Fallback: if incoming `family_id` is None, use `resource_kind`. Column count: 18 → 20.

**`bulk_upsert_capabilities()` (line 438):** Same — add `domain_id`, `family_id` to column list + parametrized values.

**`load_from_manifest_batch()` (line 732):** Add `domain_id`, `family_id` to capability INSERT.

**`_row_to_capability()` (~line 1165):** Add `domain_id=row["domain_id"]`, `family_id=row.get("family_id")`.

**FTS5 rebuild:** Drop old `capabilities_fts`, recreate with taxonomy columns:

```sql
DROP TABLE IF EXISTS capabilities_fts;
CREATE VIRTUAL TABLE capabilities_fts USING fts5(
    capability_name, description, family_id, connector_id, domain_id,
    content='capabilities', content_rowid='rowid'
);
```

**Index update** (`idx_capability_lookup`, line 226): Drop old, create new with `domain_id` + `family_id`:

```sql
DROP INDEX IF EXISTS idx_capability_lookup;
CREATE INDEX idx_capability_lookup ON capabilities(
    family_id, resource_kind, invocation_mode, effect, domain_id,
    connector_id, record_type, safety_band_min
);
```

### Issue 22.7 — GPS Query Methods For Taxonomy

- **File:** `k1/fabric/stores/global_projection_store.py`

Four new methods added to the `GlobalProjectionStore` class:

```python
def get_domains(self) -> list[str]:
    """All registered domain IDs, alphabetical."""
    ...

def get_resource_families_for_domain(self, domain_id: str) -> list[dict]:
    """Returns [{family_id, label, description}] for families valid in domain.
    JOINs resource_families ↔ domain_resource_families."""
    ...

def get_connector_resource_families(self, connector_id: str) -> list[str]:
    """Returns family_id list for a connector from connector_resource_families."""
    ...

def search_capabilities_by_text(
    self, query: str, domain_id: str = "", top_k: int = 5
) -> list[dict]:
    """FTS5 BM25 search on capabilities_fts. Domain-scoped when domain_id provided.
    Returns [{capability_name, connector_id, family_id, description, rank}]."""
    ...
```

### Issue 22.8 — Update `manifest_translator.py` + `registry.py`

- **File:** `k1/fabric/manifest_translator.py`

| Line | Change |
|------|--------|
| 311 | `domain = "family"` → `domain = getattr(definition, "domain_id", None) or "family"` |
| 313-315 | `resource_kinds` derivation — also capture `family_ids` from `definition.resource_families` if present |
| ~340-360 | `CapabilityRecord(...)` construction — add `domain_id=domain, family_id=primary_family_id` |
| after ~360 | **New:** INSERT into `connector_resource_families` for each `family_id` |
| ~362-372 | `capability_type_index` upsert — already has `domain` param, now also pass `resource_family=family_id` |

- **File:** `k1/tools/family/registry.py`

| Line | Change |
|------|--------|
| 143 | `register_definition_to_store(svc.DEFINITION, gps)` — no signature change; the `ToolDefinition` already carries `resource_families` (added in Epic 23.1, but can be added as optional here for forward compat) |

- **File:** `k1/tools/family/definition.py`

| Change |
|--------|
| Add `resource_families: list[str] | None = None` to `ToolDefinition` dataclass. `resource_kinds` stays for backward compat. |

### Issue 22.9 — Update `_build_registry_hints()` in KernelService

- **File:** `k1/kernel/service.py:2358`

Replace the two existing queries:

| Old | New |
|-----|-----|
| `SELECT DISTINCT substr(connector_id, 1, instr(...)) FROM connectors` | `SELECT domain_id FROM domains ORDER BY domain_id` |
| `SELECT DISTINCT resource_kind FROM capabilities WHERE resource_kind IS NOT NULL` | `gps.get_resource_families_for_domain(d)` per domain |

Return shape changes from `{"domains": [...], "resource_families": [...]}` to `{"domains": [...], "domain_families": {domain: [{family_id, label, description}, ...]}}`.

### Issue 22.10 — Tests

- **GAP-P2-033:** `tests/k1/fabric/stores/test_taxonomy_schema.py` (NEW)

| # | Test | What It Proves |
|---|------|---------------|
| 1 | `test_domains_table_exists_and_seeded` | 16 rows after `open()` |
| 2 | `test_resource_families_table_exists_and_seeded` | 55+ rows |
| 3 | `test_domain_resource_families_seeded` | 100+ mappings, FK constraints enforce valid refs |
| 4 | `test_connector_resource_families_empty_initially` | Table exists, 0 rows pre-bootstrap |
| 5 | `test_connectors_migration_added_domain_id` | Column present, populated from connector_id prefix |
| 6 | `test_capabilities_migration_added_domain_id_and_family_id` | Both columns present, populated from connectors JOIN + resource_kind |
| 7 | `test_resource_kind_still_exists` | Old column not dropped, both coexist |
| 8 | `test_family_id_matches_resource_kind` | For existing rows, `family_id == resource_kind` |
| 9 | `test_upsert_connector_with_invalid_domain_fails` | FK constraint fires (or app-level validation rejects it) |
| 10 | `test_upsert_capability_populates_both_family_id_and_resource_kind` | New writes set both columns |
| 11 | `test_get_resource_families_for_domain_family` | Returns event, task, chore, item, recipe for family domain |
| 12 | `test_search_capabilities_by_text_finds_shopping` | FTS5 on "add beer" finds shopping capability |
| 13 | `test_register_definition_creates_connector_resource_families` | End-to-end: manifest_translator writes connector_resource_families |
| 14 | `test_fts5_rebuilt_with_family_id_and_domain_id` | capabilities_fts contains domain_id + family_id columns |

- **Run:** `pytest tests/k1/fabric/stores/test_taxonomy_schema.py -v`

---

### Files Touched — Exact List

| File | Lines Changed | What |
|------|-------------|------|
| `k1/fabric/stores/global_projection_store.py` | ~80 lines added, ~40 lines modified | 4 new CREATE TABLEs + 3 seed loops, 2 ALTER TABLE migrations + 2 UPDATE migrations, 2 dataclass field additions, 6 method signature updates, 4 new query methods, FTS5 drop+recreate, index drop+recreate |
| `k1/fabric/manifest_translator.py` | ~15 lines modified | `domain` derivation (no longer hardcoded), `family_id` on `CapabilityRecord`, `connector_resource_families` INSERT loop |
| `k1/kernel/service.py` | ~10 lines modified | `_build_registry_hints` — query `domains` table + per-domain family query, new return shape |
| `k1/tools/family/definition.py` | 1 field added | `resource_families: list[str] \| None = None` on `ToolDefinition` |
| `tests/k1/fabric/stores/test_taxonomy_schema.py` | NEW (14 tests) | Full schema migration validation |

---

## Epic 23: Migrate Family Tool Definitions

**Goal:** Update all 6 family tool definitions to declare `domain_id` + `resource_families`. Fix `entity_type` inconsistencies. Mechanical migration — no behavior changes, no GPS writes change.

### Codebase Reality (Pre-Epic State)

| Adapter | File:Line | `entity_type` | `resource_kinds` | `domain_id` | `resource_families` | Actions |
|---------|-----------|---------------|------------------|-------------|---------------------|---------|
| Calendar | `calendar/definition.py:390` | `"calendar_event"` | `["calendar_event", "appointment"]` | ✗ (not a field) | ✗ (not a field) | 10 |
| Chores | `chores/definition.py:392` | `"chore_occurrence"` | `["chore"]` | ✗ | ✗ | 9 |
| Family Settings | `family_settings/definition.py:49` | ✗ (defaults `""`) | ✗ (not set) | ✗ | ✗ | 4 |
| Reminders | `reminders/definition.py:326` | `"reminder"` | `["reminder"]` | ✗ | ✗ | 8 |
| Shopping | `shopping/definition.py:294` | `"shopping_item"` | `["shopping_item"]` | ✗ | ✗ | 11 |
| Tasks | `tasks/definition.py:320` | `"task_item"` | `["task"]` | ✗ | ✗ | 10 |

**`ToolDefinition` dataclass** (`definition.py:295`): 24 fields. Has `resource_kinds: Optional[list[str]]` at **line 405**. **No** `resource_families` field. **No** `domain_id` field.

**`ActionSpec`** (`definition.py`, ~line 150): Uses `kind` (read/write/delete/compute), `min_band`, `allowed_roles`, `idempotent`, `side_effects`. Does NOT have `invocation_mode` or `effects` — those are resolver/graph abstractions, not on the definition dataclass.

**`manifest_translator.py:311`**: Hardcodes `domain = "family"` — will change in Epic 22.8 to read from `definition.domain_id`. Once Epic 22 lands, setting `domain_id` on definitions makes this dynamic.

**Discovery** (`__init__.py`, lines 93-125): Adapters are NOT imported directly. They are discovered via `family_tool_service_paths` config entries and loaded by `bootstrap_family_tools()` at `kernel/service.py:2344`.

---

### Issue 23.1 — Add `domain_id` + `resource_families` to `ToolDefinition`

- **File:** `k1/tools/family/definition.py` — `ToolDefinition` class, after line 405 (after `resource_kinds`)

**Two new fields:**

```python
# Line ~406 (after existing resource_kinds at L405)
resource_families: Optional[list[str]] = None   # Phase 2.6: taxonomy family IDs (e.g., ["event","task"])
domain_id: Optional[str] = None                  # Phase 2.6: taxonomy domain (e.g., "family")
```

**Do NOT remove or rename `resource_kinds`.** Both fields coexist during transition. `manifest_translator.py` reads `resource_families` first, falls back to `resource_kinds` (Epic 22.8 already handles this). A future cleanup Epic deprecates `resource_kinds`.

**`ActionSpec`**: No changes. `kind`/`min_band`/`side_effects` are the definition-level fields; `invocation_mode`/`effect` are resolver-level abstractions derived during `register_definition_to_store()`.

---

### Issue 23.2 — Migrate Calendar: `["calendar_event","appointment"]` → `["event"]`

- **File:** `k1/tools/family/calendar/definition.py`, line ~405 (where `resource_kinds` is set in `CALENDAR_DEFINITION`)

| Field | Old Value | New Value |
|-------|----------|-----------|
| `resource_kinds` | `["calendar_event", "appointment"]` | **unchanged** (keep for backward compat) |
| `resource_families` | ✗ (not set) | `["event"]` |
| `domain_id` | ✗ (not set) | `"family"` |
| `entity_type` | `"calendar_event"` | **unchanged** (this is the local projection row type, not the taxonomy family) |

**Why entity_type stays:** `entity_type="calendar_event"` names the local SQLite projection table row. That's a different concept from taxonomy `family_id="event"`. The two should align conceptually but don't have to be identical strings — `manifest_translator.py` maps `resource_families` → `family_id` on the `CapabilityRecord`.

**No action changes.** All 10 actions unchanged.

---

### Issue 23.3 — Migrate Tasks: Fix `entity_type`

- **File:** `k1/tools/family/tasks/definition.py`, line ~328 and ~364 (where `entity_type` and `resource_kinds` are set in `TASKS_DEFINITION`)

| Field | Old Value | New Value |
|-------|----------|-----------|
| `entity_type` | `"task_item"` | `"task"` |
| `resource_kinds` | `["task"]` | **unchanged** |
| `resource_families` | ✗ | `["task"]` |
| `domain_id` | ✗ | `"family"` |

**Why fix entity_type:** `entity_type="task_item"` is inconsistent — the adapter is `tasks`, the resource_kind is `task`, the capability names say `tool.execute.family.tasks.create_task`. `entity_type` should match the adapter's canonical entity name: `"task"`.

**Regression risk:** `entity_type` appears in projection SQL (`tables_sql`), `can_reference` lists on other adapters, and `filters` definitions. Verify `tables_sql` uses `task` not `task_item` — if it references `task_item`, update the DDL column/table names too.

**No action changes.** All 10 actions unchanged.

---

### Issue 23.4 — Migrate Reminders: `["reminder"]` → `["reminder"]`

- **File:** `k1/tools/family/reminders/definition.py`, line ~365 (where `resource_kinds` is set in `REMINDERS_DEFINITION`)

| Field | Old Value | New Value |
|-------|----------|-----------|
| `resource_kinds` | `["reminder"]` | **unchanged** |
| `resource_families` | ✗ | `["reminder"]` |
| `domain_id` | ✗ | `"family"` |

**Same name, different semantics:** `resource_kinds=["reminder"]` was a connector-specific string. `resource_families=["reminder"]` means "this connector operates on the `reminder` resource family registered in the `resource_families` taxonomy table." The GPS now validates it via FK.

**No action changes.** All 8 actions unchanged. `entity_type="reminder"` is already correct.

---

### Issue 23.5 — Migrate Chores: Fix `entity_type`

- **File:** `k1/tools/family/chores/definition.py`, line ~328 and ~431 (where `entity_type` and `resource_kinds` are set in `CHORES_DEFINITION`)

| Field | Old Value | New Value |
|-------|----------|-----------|
| `entity_type` | `"chore_occurrence"` | `"chore"` |
| `resource_kinds` | `["chore"]` | **unchanged** |
| `resource_families` | ✗ | `["chore"]` |
| `domain_id` | ✗ | `"family"` |

**Why fix entity_type:** Same as Tasks — `entity_type="chore_occurrence"` is inconsistent with adapter name `chores`, resource_kind `chore`, and capability names like `tool.execute.family.chores.assign_chore`.

**Regression risk:** Check `tables_sql` for `chore_occurrence` references. Check `can_reference` on other adapters that may reference `chore_occurrence`.

**No action changes.** All 9 actions unchanged.

---

### Issue 23.6 — Migrate Shopping: `["shopping_item"]` → `["item"]`

- **File:** `k1/tools/family/shopping/definition.py`, line ~338 (where `resource_kinds` is set in `SHOPPING_DEFINITION`)

| Field | Old Value | New Value |
|-------|----------|-----------|
| `resource_kinds` | `["shopping_item"]` | **unchanged** |
| `resource_families` | ✗ | `["item"]` |
| `domain_id` | ✗ | `"family"` |

**Why `item`:** Taxonomy family is `item` (real-world concept: a purchasable item), not `shopping_item` (connector implementation detail). The `resource_families` taxonomy table has `item` as a cross-domain family shared by shopping, food, entertainment domains.

**No action changes.** All 11 actions unchanged. `entity_type="shopping_item"` stays (projection row type).

---

### Issue 23.7 — Migrate Family Settings: Add Missing Fields

- **File:** `k1/tools/family/family_settings/definition.py`, line ~49-120 (the full `FAMILY_SETTINGS_DEFINITION`)

| Field | Old Value | New Value |
|-------|----------|-----------|
| `entity_type` | ✗ (defaults `""`) | `"family_setting"` |
| `resource_kinds` | ✗ (not set) | `["setting"]` |
| `resource_families` | ✗ | `["setting"]` |
| `domain_id` | ✗ | `"family"` |
| `actor_scope` | ✗ (not set) | `["parent", "admin", "system"]` |
| `domain_tags` | ✗ (not set) | `["configuration", "policy", "feature_flags"]` |

**Why missing:** Family Settings is the newest adapter. It was added after Phase 1.1 catalog bootstrap. It never had `resource_kinds`, `entity_type`, or enrichment fields. Epic 23 adds them.

**No action changes.** All 4 actions unchanged.

---

### Issue 23.8 — Fix Stale `can_reference` Values

**Files:** `k1/tools/family/chores/definition.py:390`, `k1/tools/family/shopping/definition.py:302`

The subagent found TWO adapters with stale cross-references:

| Adapter | Line | Current `can_reference` | Stale Value | Fix |
|---------|------|------------------------|-------------|-----|
| **Chores** | ~390 | `["task_item", "calendar_event", "reminder"]` | `"task_item"` | → `"task"` |
| **Shopping** | ~302 | `["task_item", "calendar_event", "reminder"]` | `"task_item"` | → `"task"` |

**Why `"task_item"` is stale:** Tasks adapter's `resource_kinds` is `["task"]`, and after Issue 23.3, `entity_type` becomes `"task"`. Chores and Shopping still reference the legacy `entity_type` value `"task_item"` — this creates a cross-reference mismatch.

**Fix:** Replace `"task_item"` → `"task"` in both `can_reference` lists.

**No references to `"chore_occurrence"` found** — only `"task_item"` is stale. Calendar, Tasks, and Reminders `can_reference` lists are clean.

**Family Settings** has no `can_reference` at all — gets `can_reference: []` (empty, valid — settings don't reference other adapters).

---

### Issue 23.9 — Tests

- **GAP-P2-034:** `tests/k1/tools/family/test_taxonomy_migration.py` (NEW)
- **GAP-P2-034b:** Full regression: `tests/k1/tools/family/` (all existing tests)

| # | Test | What It Proves |
|---|------|---------------|
| 1 | `test_all_6_definitions_have_domain_id` | Every DEFINITION sets `domain_id="family"` |
| 2 | `test_all_6_definitions_have_resource_families` | Every DEFINITION sets `resource_families` (non-empty list) |
| 3 | `test_resource_families_values_match_taxonomy` | Calendar→`["event"]`, Tasks→`["task"]`, Reminders→`["reminder"]`, Chores→`["chore"]`, Shopping→`["item"]`, Settings→`["setting"]` |
| 4 | `test_resource_kinds_still_present` | Old field not removed from any definition |
| 5 | `test_entity_types_are_canonical` | Tasks=`"task"` (not `"task_item"`), Chores=`"chore"` (not `"chore_occurrence"`), Settings=`"family_setting"` (not `""`) |
| 6 | `test_entity_type_in_tables_sql` | Each adapter's `tables_sql` uses the same name as `entity_type` |
| 7 | `test_can_reference_no_stale_entity_types` | No definition's `can_reference` contains `"task_item"` or `"chore_occurrence"` |
| 8 | `test_family_settings_has_enrichment_fields` | `entity_type`, `actor_scope`, `domain_tags` are all set |
| 9 | `test_register_definition_produces_family_id` | After `register_definition_to_store()`, GPS capability rows have `family_id` matching `resource_families[0]` |

- **Run:** `pytest tests/k1/tools/family/test_taxonomy_migration.py -v`
- **Regression:** `pytest tests/k1/tools/family/ -v`

---

### Files Touched — Exact List

| File | Lines Changed | What |
|------|-------------|------|
| `k1/tools/family/definition.py` | +2 fields | `resource_families` + `domain_id` on `ToolDefinition` (after L393 `resource_kinds`) |
| `k1/tools/family/calendar/definition.py` | +2 lines | `domain_id="family"`, `resource_families=["event"]` near L419 |
| `k1/tools/family/tasks/definition.py` | +3 lines, 2 modified | `domain_id`, `resource_families`, `entity_type="task"` fixed (L335), `can_reference` clean (L340) |
| `k1/tools/family/reminders/definition.py` | +2 lines | `domain_id="family"`, `resource_families=["reminder"]` near L341 |
| `k1/tools/family/chores/definition.py` | +3 lines, 2 modified | `domain_id`, `resource_families`, `entity_type="chore"` fixed (L385), `can_reference` fix `"task_item"`→`"task"` (L390) |
| `k1/tools/family/shopping/definition.py` | +3 lines, 1 modified | `domain_id`, `resource_families=["item"]`, `can_reference` fix `"task_item"`→`"task"` (L302) |
| `k1/tools/family/family_settings/definition.py` | +5 lines | `domain_id`, `resource_families`, `entity_type`, `actor_scope`, `domain_tags` (all new — adapter had zero enrichment) |
| `tests/k1/tools/family/test_taxonomy_migration.py` | NEW (9 tests) | Definition-level validation |

**Pre-existing enrichment gaps in Family Settings** (for future Epics, not blocking Epic 23):

- ❌ `constitution`, `policy_declarations`, `guide_cards`, `ontology` — all absent
- ❌ `snapshot_types`, `back_execution_profile`, `activity_profile` — all absent
- These are Phase 1.1 enrichment fields. Family Settings was added after Phase 1.1. A future Epic should backfill them.

---

## Epic 24: Resolver — Domain-Scoped Graph + FTS5 Fallback

**Goal:** Wire FTS5 BM25 search as a fallback inside `CapabilityTypeResolver._resolve_one()` when structured graph queries return empty. FTS5 infrastructure already exists — this is a surgical wiring change, not a build-from-scratch.

### Codebase Reality (Pre-Epic State)

**FTS5 infrastructure — FULLY BUILT:**

| Component | File:Line | Status |
|-----------|-----------|--------|
| `capabilities_fts` virtual table | `global_projection_store.py:207-212` | ✅ Content-sync FTS5 on `capabilities(capability_name, description, resource_kind, connector_id)` |
| `search_capabilities(query, top_k, connector_ids)` | `global_projection_store.py:532-558` | ✅ BM25-ranked, returns `list[CapabilityRecord]` |
| `search_capabilities_by_domain(query, domains, top_k)` | `global_projection_store.py:560-583` | ✅ Domain-scoped via `connector_id LIKE '{domain}.%'` |
| `_sanitize_fts_query(query)` | `global_projection_store.py:518-530` | ✅ Strips unsafe FTS5 chars |
| `rebuild_fts_index()` | `global_projection_store.py:585-587` | ✅ Called after every upsert/bulk/delete |
| FTS5 used in binder Pass 3 (BM25) | `capability_binder.py` (3-pass discovery) | ✅ Binder already falls back to FTS5 |

**Graph resolution — FULLY BUILT:**

| Component | File:Line | Status |
|-----------|-----------|--------|
| `_resolve_one()` 4-step graph traversal | `capability_type_resolver.py:130-249` | ✅ Steps 1-4 with domain-agnostic fallbacks |
| `_resolve_operation()` verb→(op_family, effect) | `capability_type_resolver.py:253-284` | ✅ `UNIVERSAL_OPERATION_ALIASES` + graph + frozenset + first-word fallback |
| `_resolve_concept()` concept alias→canonical | `capability_type_resolver.py:288-313` | ✅ With domain filter + domain-agnostic fallback |
| `get_concept_resource_family(concept, domain)` | `global_projection_store.py:~952-967` | ✅ `concept_resource_edges` graph table |
| `lookup_capability_by_type(domain, rf, op, effect)` | `global_projection_store.py:~986-998` | ✅ `capability_type_index` with domain column |
| Domain-agnostic fallback in all 4 steps | `capability_type_resolver.py:184-186,192-194,205-213` | ✅ Already wired |
| Step 11b empty-binding gate | `situated_resolver.py:533-540` | ✅ Prevents `can_execute` with empty plan |

**THE GAP — FTS5 NEVER CALLED FROM `CapabilityTypeResolver`:**

- `_resolve_one()` computes `confidence` (low/medium/high) at line 242-246 but **never uses it** to trigger FTS5
- When `lookup_capability_by_type()` returns empty at Step 4 (line 236-240), **no FTS5 fallback is invoked**
- The class docstring says "Fallback: when graph confidence is low, delegates to FTS5 BM25 search" — **this is unimplemented**
- Grep confirms: `search`, `fts`, `fts5` do not appear anywhere in `capability_type_resolver.py`
- The gap is narrow: ~15-20 lines of new code to wire `search_capabilities_by_domain()` as a Step 4 fallback

### `CapabilityTypeResolver` — Constructor Change Needed

**File:** `k1/fabric/resolver/capability_type_resolver.py`, line 112-116

Current:

```python
def __init__(self, global_store: GlobalProjectionStore, local_store: LocalProjectionStore) -> None:
    self.global_store = global_store
    self.local_store = local_store
```

`search_capabilities_by_domain()` is already on `global_store` — no constructor change needed. The resolver already has access.

### Issue 24.1 — Add FTS5 Fallback in `_resolve_one()` Step 4

- **File:** `k1/fabric/resolver/capability_type_resolver.py`, lines 224-240 (Step 4: Typed Capability Lookup)

**Current code (lines 224-240):**

```python
        # Step 4: Typed capability lookup
        capabilities: list[dict[str, Any]] = []
        if resource_family and op_family:
            caps = self.global_store.lookup_capability_by_type(
                domain=domain, resource_family=resource_family,
                operation_family=op_family, effect=effect)
            if not caps and domain:
                caps = self.global_store.lookup_capability_by_type(
                    domain="", resource_family=resource_family,
                    operation_family=op_family, effect=effect)
            if caps:
                capabilities = caps
                evidence.append(f"typed_lookup: {domain}.{resource_family}.{op_family}.{effect} → {len(caps)} matches")
```

**New code — add FTS5 fallback after empty graph lookup:**

```python
        # Step 4: Typed capability lookup
        capabilities: list[dict[str, Any]] = []
        if resource_family and op_family:
            caps = self.global_store.lookup_capability_by_type(
                domain=domain, resource_family=resource_family,
                operation_family=op_family, effect=effect)
            if not caps and domain:
                caps = self.global_store.lookup_capability_by_type(
                    domain="", resource_family=resource_family,
                    operation_family=op_family, effect=effect)
            if caps:
                capabilities = caps
                evidence.append(f"typed_lookup: {domain}.{resource_family}.{op_family}.{effect} → {len(caps)} matches")
            else:
                # FTS5 fallback: graph returned empty → try BM25 text search
                fts_results = self.global_store.search_capabilities_by_domain(
                    query=action, domains=[domain] if domain else [],
                    top_k=5)
                if fts_results:
                    capabilities = [
                        {
                            "capability_name": c.capability_name,
                            "connector_id": c.connector_id,
                            "resource_kind": c.resource_kind,
                            "invocation_mode": c.invocation_mode,
                            "effect": c.effect,
                            "_source": "fts5",
                        }
                        for c in fts_results
                    ]
                    evidence.append(
                        f"fts5_fallback: '{action[:60]}' domain={domain or '*'} "
                        f"→ {len(capabilities)} matches"
                    )
                    # Override confidence when using FTS5 fallback
                    conf = "medium" if len(capabilities) >= 1 else conf
```

**What changes:**

1. After `lookup_capability_by_type()` returns empty with both domain and domain-agnostic attempts, call `search_capabilities_by_domain(action_text, [domain], top_k=5)`
2. Convert `CapabilityRecord` dataclass instances to dicts matching `fallback_capabilities` format
3. Tag with `_source: "fts5"` for observability
4. Boost confidence to `"medium"` when FTS5 finds matches

**Edge cases:**

- If `action` is empty: skip FTS5 (no query string). Keep empty capabilities.
- If `domain` is empty: call `search_capabilities(query=action, top_k=5)` (no domain filter) instead of `search_capabilities_by_domain()`
- If FTS5 returns >5 results: binder Pass 3 will re-run FTS5 anyway — this is just a type-hint layer

### Issue 24.2 — Add `search_capabilities` Import Path

- **File:** `k1/fabric/resolver/capability_type_resolver.py`, lines 12-18 (imports)

No new imports needed. `search_capabilities_by_domain()` and `search_capabilities()` are methods on `GlobalProjectionStore`, which is already available as `self.global_store`. The `CapabilityRecord` dataclass is in `global_projection_store.py` — already imported if referenced by name.

### Issue 24.3 — Confidence-Based FTS5 Routing (Optional Enhancement)

- **File:** `k1/fabric/resolver/capability_type_resolver.py`, after line 246 (confidence scoring)

After confidence is computed (lines 242-246), optionally trigger FTS5 for low-confidence resolutions even if graph returned results:

```python
        # Optional: if confidence is "low" and we have a domain, try FTS5
        # to supplement or replace the graph results
        if conf == "low" and action and domain and len(capabilities) <= 2:
            fts_results = self.global_store.search_capabilities_by_domain(
                query=action, domains=[domain], top_k=3)
            if fts_results:
                fts_caps = [
                    {
                        "capability_name": c.capability_name,
                        "connector_id": c.connector_id,
                        "resource_kind": c.resource_kind,
                        "invocation_mode": c.invocation_mode,
                        "effect": c.effect,
                        "_source": "fts5_boost",
                    }
                    for c in fts_results
                ]
                # Merge: deduplicate by capability_name, FTS5 first then graph
                seen = {c["capability_name"] for c in fts_caps}
                for c in capabilities:
                    if c.get("capability_name") not in seen:
                        fts_caps.append(c)
                capabilities = fts_caps
                evidence.append(f"fts5_boost: confidence was low, supplemented with {len(fts_caps)} results")
                conf = "medium"
```

**This is optional.** The core fix (Issue 24.1) handles the primary failure mode: graph returns empty. This enhancement handles the case where graph returns something but with low confidence. Can be deferred to a future iteration.

### Issue 24.4 — Verify Binder Pass 3 Integration

- **File:** `k1/fabric/resolver/capability_binder.py` (3-pass discovery, ~line 178+)

**No changes needed.** The binder's Pass 3 already calls `global_store.search_capabilities(query=action_text)` independently. The FTS5 results we add to `fallback_capabilities` in `_resolve_one()` become Pass 1 (typed) candidates for the binder — the binder will deduplicate if Pass 3 finds the same capabilities.

**Verification:** Confirm that `ResolvedIntentType.fallback_capabilities` (line 98, `list[dict[str, Any]]`) flows into `CapabilityBinderService.bind()` as typed candidates. Trace: `ResolveSituationService.resolve()` line 288 → `intent_types` → line 293 `self.capability_binder.bind(intent_types, ...)` → binder reads `resolved.fallback_capabilities` for Pass 1.

### Issue 24.5 — Tests

- **GAP-P2-035:** `tests/k1/fabric/resolver/test_fts5_fallback.py` (NEW)
- **GAP-P2-035b:** Regression: `tests/k1/fabric/resolver/` (all existing resolver tests)

| # | Test | What It Proves |
|---|------|---------------|
| 1 | `test_fts5_fallback_when_graph_empty` | GPS has FTS5 match for "buy groceries" → `_resolve_one()` returns capabilities with `_source: "fts5"` |
| 2 | `test_fts5_fallback_preserves_domain_scoping` | FTS5 results for domain="family" exclude finance connectors |
| 3 | `test_fts5_fallback_no_match` | GPS has no FTS5 match for nonsense query → capabilities stays empty, confidence stays "low" |
| 4 | `test_fts5_fallback_empty_action_skips` | `action=""` → no FTS5 call, no crash |
| 5 | `test_fts5_fallback_empty_domain` | `domain=""` → calls `search_capabilities()` (no domain filter) instead of `search_capabilities_by_domain()` |
| 6 | `test_fts5_results_format_matches_fallback_capabilities` | FTS5 result dicts have `capability_name`, `connector_id`, `resource_kind`, `invocation_mode`, `effect`, `_source` keys |
| 7 | `test_confidence_boosted_to_medium_on_fts5_match` | FTS5 finds results → confidence="medium" even with only 1 evidence item |
| 8 | `test_binder_receives_fts5_fallback_capabilities` | `ResolvedIntentType.fallback_capabilities` populated from FTS5 → binder Pass 1 sees them |

- **Run:** `pytest tests/k1/fabric/resolver/test_fts5_fallback.py -v`
- **Regression:** `pytest tests/k1/fabric/resolver/ -v -p no:xdist -p no:cacheprovider`

---

### Files Touched — Exact List

| File | Lines Changed | What |
|------|-------------|------|
| `k1/fabric/resolver/capability_type_resolver.py` | +15-20 lines (after L240) | FTS5 fallback in `_resolve_one()` Step 4; optional confidence-based boost |
| `tests/k1/fabric/resolver/test_fts5_fallback.py` | NEW (8 tests) | FTS5 fallback validation |
| `k1/fabric/resolver/capability_binder.py` | 0 lines (verify only) | Confirm `fallback_capabilities` flows to binder Pass 1 |
| `k1/fabric/stores/global_projection_store.py` | 0 lines | `search_capabilities_by_domain()` already exists at L560-583 |

### What This Epic Does NOT Do

- ❌ Does NOT create FTS5 tables (already exist)
- ❌ Does NOT add new GPS methods (already exist)
- ❌ Does NOT change binder Pass 3 (already uses FTS5)
- ❌ Does NOT change `situated_resolver.py` (step 11b already in place)
- ❌ Does NOT add `family_id` to the resolver (that's a future multi-family-scoping Epic)
- ❌ Does NOT fix `capability_type_index.domain` PK issue (low-priority, deferred)

### Summary

Epic 24 is a **~20-line surgical change** to `_resolve_one()`. The full FTS5 infrastructure, domain-scoped search, BM25 ranking, query sanitization, and index rebuild pipeline are already built and production-tested in the binder. The resolver just needs to call them.

---

## Epic 25: Back Prompt — Domain-Scoped Live Rendering

**Goal:** Replace the flat comma-joined domain/family lists in Back's prompt with per-domain grouped family lists with 1-line descriptions, queried live from the new `domains` + `resource_families` taxonomy tables (Epic 22). No hardcoded lists. The Back LLM sees which families belong to which domain.

### Codebase Reality (Pre-Epic State)

**`_build_registry_hints()`** — `k1/kernel/service.py:2358-2391`:

- Queries domains via `substr(connector_id, 1, instr(connector_id, '.') - 1)` from `connectors` table — a string-manipulation hack
- Queries resource_families via `SELECT DISTINCT resource_kind FROM capabilities` — flat list, no domain association
- Returns `{"domains": ["family", ...], "resource_families": ["calendar_event", "chore", ...]}` — two independent flat lists

**`build_back_prompt()`** — `k1/concierge/prompt/back_prompt.py:449-471`:

- Builds `registry_hints_narrative` = `"Currently registered domains: family, health, ..."` (comma-joined)
- Builds `registry_resource_families_narrative` = `"Currently registered resource families: calendar_event, chore, ..."` (comma-joined)
- No per-domain association. LLM can't tell that `calendar_event` belongs to `family` vs `health`.

**`BACK_SYSTEM_PROMPT`** — `k1/concierge/prompt/back_prompt.py:121-137`:

- Placeholder `{registry_hints_narrative}` at line 129 (domain list)
- Placeholder `{registry_resource_families_narrative}` at line 135 (resource_family list)
- No `{registry_family_narrative}` placeholder exists

**End-to-end flow is fully wired:**

```
Kernel._build_registry_hints() → PortBundle.registry_hints → Factory → Runtime.set_registry_hints()
→ _back_consumer() → route_back_envelope() → back_handler() → build_back_prompt()
```

All plumbing is in place — only the dict shape and narrative formatting need to change.

### Issue 25.1 — Update `_build_registry_hints()` to Query Taxonomy Tables

- **File:** `k1/kernel/service.py`, lines 2358-2391

**Replace the `substr(connector_id)` hack with queries against the Epic 22 taxonomy tables:**

```python
def _build_registry_hints(gps: Any) -> dict[str, Any]:          # line 2358
    """Query GPS taxonomy tables for live domain + resource family metadata.

    Queries the ``domains``, ``resource_families``, and ``domain_resource_families``
    tables created in Epic 22. Returns a nested dict: each domain has a list of
    families with label and description.
    """
    hints: dict[str, Any] = {"domains": [], "resource_families": []}   # line 2368
    try:
        # Query domains table (Epic 22)
        rows = gps._db.execute(
            "SELECT domain_id, label, description FROM domains ORDER BY domain_id"
        ).fetchall()
        hints["domains"] = [
            {"domain_id": r[0], "label": r[1], "description": r[2]}
            for r in rows
        ]
    except Exception:
        # Fallback: if domains table doesn't exist yet (pre-Epic-22 GPS),
        # use the old substr hack
        try:
            rows = gps._db.execute(
                "SELECT DISTINCT "
                "  CASE WHEN instr(connector_id, '.') > 0 "
                "    THEN substr(connector_id, 1, instr(connector_id, '.') - 1) "
                "    ELSE connector_id END AS domain "
                "FROM connectors ORDER BY domain"
            ).fetchall()
            hints["domains"] = [
                {"domain_id": r[0], "label": r[0].title(), "description": ""}
                for r in rows if r[0]
            ]
        except Exception:
            pass

    try:
        # Query per-domain family lists (Epic 22)
        rows = gps._db.execute(
            """SELECT d.domain_id, d.label as domain_label,
                      rf.family_id, rf.label as family_label, rf.description
               FROM domains d
               JOIN domain_resource_families drf ON d.domain_id = drf.domain_id
               JOIN resource_families rf ON drf.family_id = rf.family_id
               ORDER BY d.domain_id, rf.family_id"""
        ).fetchall()
        # Group families by domain
        by_domain: dict[str, dict[str, Any]] = {}
        for row in rows:
            did, dlabel, fid, flabel, fdesc = row
            if did not in by_domain:
                by_domain[did] = {
                    "domain_id": did,
                    "label": dlabel or did.title(),
                    "families": [],
                }
            by_domain[did]["families"].append({
                "family_id": fid,
                "label": flabel or fid,
                "description": fdesc or "",
            })
        hints["resource_families"] = list(by_domain.values())
    except Exception:
        # Fallback: flat resource_kind list from capabilities table
        try:
            rows = gps._db.execute(
                "SELECT DISTINCT resource_kind FROM capabilities "
                "WHERE resource_kind IS NOT NULL AND resource_kind != '' "
                "ORDER BY resource_kind"
            ).fetchall()
            hints["resource_families"] = [
                {"domain_id": "", "label": "", "families": [
                    {"family_id": r[0], "label": r[0], "description": ""}
                ]}
                for r in rows if r[0]
            ]
        except Exception:
            pass

    return hints
```

**New dict shape:**

```python
{
    "domains": [
        {"domain_id": "family", "label": "Family OS", "description": "Family management and coordination"},
        {"domain_id": "health", "label": "Health", "description": "Health and wellness tracking"},
        ...
    ],
    "resource_families": [
        {
            "domain_id": "family",
            "label": "Family OS",
            "families": [
                {"family_id": "event", "label": "Events", "description": "Calendar events, appointments, and meetings"},
                {"family_id": "task", "label": "Tasks", "description": "To-do items, homework, and action items"},
                {"family_id": "chore", "label": "Chores", "description": "Recurring household duties and responsibilities"},
                {"family_id": "item", "label": "Items", "description": "Shopping items, groceries, and supplies"},
                {"family_id": "reminder", "label": "Reminders", "description": "Time-based notification reminders"},
            ]
        },
        ...
    ]
}
```

**Graceful degradation:** If the Epic 22 taxonomy tables don't exist (pre-migration GPS), fall back to the old `substr` + `DISTINCT resource_kind` queries. The prompt narrative construction handles both shapes.

### Issue 25.2 — Update `build_back_prompt()` Narrative Construction

- **File:** `k1/concierge/prompt/back_prompt.py`, lines 449-471

**Replace flat comma-joined lists with per-domain grouped narrative:**

```python
    # ── Registry hints narrative (Phase 2.6: live GPS taxonomy snapshot) ──
    _rh = registry_hints or {}
    _domains = _rh.get("domains", [])
    _rfs = _rh.get("resource_families", [])

    # Domain list (compact)
    if _domains:
        _domain_names = [
            d.get("label", d.get("domain_id", "?")) if isinstance(d, dict) else str(d)
            for d in _domains
        ]
        registry_hints_narrative = (
            "    Currently registered domains: " + ", ".join(_domain_names) + "."
        )
    else:
        registry_hints_narrative = (
            "    No domain list is available — use your best judgment (e.g.,\n"
            "    family, health, finance, travel, education, work, home,\n"
            "    entertainment, food, fitness, productivity, shopping, legal)."
        )

    # Per-domain family lists with descriptions (grouped)
    if _rfs and isinstance(_rfs[0], dict) and "families" in _rfs[0]:
        # New shape: per-domain grouped families with descriptions
        lines = ["    Registered resource families by domain:"]
        for domain_entry in _rfs:
            d_label = domain_entry.get("label", domain_entry.get("domain_id", "?"))
            families = domain_entry.get("families", [])
            family_strs = []
            for f in families:
                fid = f.get("family_id", "?")
                fdesc = f.get("description", "")
                if fdesc:
                    family_strs.append(f"{fid} ({fdesc})")
                else:
                    family_strs.append(fid)
            lines.append(f"      {d_label}: {', '.join(family_strs)}")
        registry_family_narrative = "\n".join(lines)
    elif _rfs:
        # Old shape: flat list (pre-Epic-25 fallback)
        _family_names = [str(f) for f in _rfs]
        registry_family_narrative = (
            "    Currently registered resource families: " + ", ".join(_family_names) + "."
        )
    else:
        registry_family_narrative = (
            "    No resource family list is available — use your best judgment.\n"
            "    Describe what the user is acting on as a noun phrase (e.g.,\n"
            "    calendar_event, task, reminder, shopping_item, contact,\n"
            "    message, document, subscription, reservation)."
        )
```

**What changes:**

1. Detects dict shape: if `resource_families[0]` has `"families"` key → new grouped format; else → legacy flat format
2. Produces compact grouped narrative: `family: event (appointments), task (to-dos), chore (duties)`
3. ~500 chars total for typical 16-domain, 3-5 families/domain configuration

### Issue 25.3 — Update `BACK_SYSTEM_PROMPT` Template

- **File:** `k1/concierge/prompt/back_prompt.py`, lines 121-137

**Add `{registry_family_narrative}` placeholder. Keep `{registry_hints_narrative}` and remove `{registry_resource_families_narrative}`:**

Current:

```
  domain (RECOMMENDED — your best guess at the broad category):
{registry_hints_narrative}

  resource_family (RECOMMENDED — what kind of thing?):
    Describe what the user is trying to act on as a noun phrase.
    Use one of the registered families when it clearly fits; invent
    a descriptive noun phrase when nothing matches.
{registry_resource_families_narrative}
```

New:

```
  domain (RECOMMENDED — your best guess at the broad category):
{registry_hints_narrative}

  resource_family (RECOMMENDED — what kind of thing?):
    Describe what the user is trying to act on as a noun phrase.
    Use one of the registered families when it clearly fits; invent
    a descriptive noun phrase when nothing matches.
{registry_family_narrative}
```

**Placeholder rename:** `{registry_resource_families_narrative}` → `{registry_family_narrative}`. This is a consistent rename: the narrative now conveys families grouped by domain, not just a flat resource list.

### Issue 25.4 — Update `.format()` Wiring

- **File:** `k1/concierge/prompt/back_prompt.py`, lines 489-515

Replace:

```python
        registry_resource_families_narrative=registry_resource_families_narrative,
```

With:

```python
        registry_family_narrative=registry_family_narrative,
```

Also update the header comment at lines 11-27 to list `{registry_family_narrative}` instead of `{registry_resource_families_narrative}`.

### Issue 25.5 — Backward Compatibility: Pre-Epic-22 GPS

The fallback queries in Issue 25.1 handle GPS databases that don't yet have the `domains`/`resource_families` tables. The narrative construction in Issue 25.2 handles both old (flat list) and new (grouped dict) shapes. This means:

- Kernel can boot with a pre-Epic-22 GPS and the prompt still works (flat lists)
- After Epic 22 migration runs, the next kernel boot picks up the new taxonomy tables
- No flag day, no coordinated deployment — self-healing

### Issue 25.6 — Tests

- **GAP-P2-036:** Update prompt tests for domain-scoped rendering.
- **GAP-P2-036b:** Regression: `tests/k1/concierge/prompt/` (all existing prompt tests)

| # | Test | What It Proves |
|---|------|---------------|
| 1 | `test_prompt_includes_grouped_families` | Prompt contains `family: event, task, chore` grouped format when new dict shape provided |
| 2 | `test_prompt_includes_family_descriptions` | Prompt contains `event (appointments, meetings)` description format |
| 3 | `test_prompt_falls_back_to_flat_list` | Old flat `resource_families` list still renders correctly (backward compat) |
| 4 | `test_prompt_no_registry_hints_graceful` | `registry_hints=None` → fallback text, no crash |
| 5 | `test_prompt_domain_list_from_new_shape` | `domains` as list of dicts renders correctly |
| 6 | `test_prompt_placeholder_rename` | `{registry_family_narrative}` works; old `{registry_resource_families_narrative}` removed from template |
| 7 | `test_prompt_token_budget` | Grouped narrative is under 800 chars for 16 domains × 5 families |

- **Run:** `pytest tests/k1/concierge/prompt/test_back_prompt.py -v -k "registry or family or domain" --no-cov`
- **Regression:** `pytest tests/k1/concierge/prompt/ -v -p no:xdist -p no:cacheprovider`

---

### Files Touched — Exact List

| File | Lines Changed | What |
|------|-------------|------|
| `k1/kernel/service.py` | ~40 lines (L2358-2391 replaced) | `_build_registry_hints()` — query taxonomy tables, new dict shape, fallback queries |
| `k1/concierge/prompt/back_prompt.py` | ~30 lines (L121-137 template, L449-471 narrative, L489-515 format) | New `{registry_family_narrative}` placeholder, grouped narrative construction, backward-compat detection |
| `tests/k1/concierge/prompt/test_back_prompt.py` | ~7 new tests | Domain-scoped rendering validation |

### What This Epic Does NOT Do

- ❌ Does NOT change the Back prompt's execution protocol (RESOLVE→EXECUTE→SUBMIT stays)
- ❌ Does NOT add new GPS public API methods (`gps.get_domains()`, etc.) — uses direct `_db.execute()` consistent with existing pattern
- ❌ Does NOT add `domain` column to `connectors` table (deferred to future Epic)
- ❌ Does NOT change `back_handler()` or `route_back_envelope()` signatures — `registry_hints` param is already wired

---

## Epic 26: Documentation — Taxonomy Contract

### Issue 26.1 — Create `RESOURCE_FAMILY_TAXONOMY.md`

- **File:** `k1/fabric/docs/RESOURCE_FAMILY_TAXONOMY.md` (new)
- Full domain table, family table, domain→family mapping. Naming conventions. How to propose new taxonomy entries.

### Issue 26.2 — Update `connector_development_external.md`

- New taxonomy section. Updated IFL manifest examples. Updated admission checklist.

### Issue 26.3 — Update `connector_onboarding_familyos.md`

- Same taxonomy reference + migration guide for existing tools.

---

## Execution Order

```
Epic 22 (GPS Schema) → Epic 23 (Family Tools) → Epic 24 (Resolver FTS5) → Epic 25 (Back Prompt) → Epic 26 (Docs) → Epic 27 (Self-Healing)
```

---

## Summary

| Epic | Issues | Files Created | Files Modified | Tests |
|------|--------|--------------|----------------|-------|
| 22 — GPS Schema | 10 | 1 (test) | 4 | 14 |
| 23 — Family Tool Migration | 9 | 1 (test) | 7 | 9 + full regression |
| 24 — Resolver FTS5 | 5 | 1 (test) | 1 | 8 |
| 25 — Back Prompt | 6 | 0 | 2 | 7 |
| 26 — Documentation | 3 | 1 (taxonomy doc) | 2 | Manual review |
| 27 — Self-Healing Ontology | 8 | 3 (learner + 2 tests) | 3 | 14 |
| **Total** | **41** | **7 new files** | **~19 modified** | **~52 new tests** |

---

## Governance

| Artifact | Controlled By | How It Changes |
|----------|--------------|---------------|
| **Domains** | FamilyOS team | PR review. Rare — new domain = new industry vertical. |
| **Resource Families** | FamilyOS team | PR review during connector admission. New family when genuinely new real-world category emerges. |
| **Domain↔Family Mapping** | FamilyOS team | Connector developer proposes; FamilyOS approves. |
| **Connector↔Family Mapping** | Connector developer | Declared in manifest. Automatic upsert at bootstrap. FK-validated. |
| **Capability Naming** | Connector developer | `tool.{mode}.{domain}.{name}.{action}`. Validated at admission. |

---

## Epic 27: Self-Healing Ontology — Bayesian Graph Learning

> **Status:** DESIGN PHASE — grounded in codebase reality, NOT yet implemented.
> **Predecessor:** Epics 22-25 (taxonomy tables, definition migration, FTS5 fallback, Back prompt).
> **Trigger:** Every FTS5 fallback success is a signal that the graph had a gap.
> **Philosophy:** Never auto-promote. Require statistical evidence. Track negative signals. Keep curated edges authoritative over learned edges.

### The Loop

```
┌──────────────────────────────────────────────────────────────────┐
│                    RESOLUTION CYCLE                               │
│                                                                   │
│  1. Graph fails (concept → resource_family edge missing)          │
│           ↓                                                       │
│  2. FTS5 save (BM25 finds capability via description text)        │
│           ↓                                                       │
│  3. Gap logged — ontology_gaps(concept, family, domain, count++)  │
│           ↓                                                       │
│  4. Back executes capability                                      │
│           ↓                                                       │
│  5. Outcome tracked — win (exec OK, no re-resolution) or          │
│     loss (exec failed, Back overrode, HIL fired)                  │
│           ↓                                                       │
│  6. Beta(α=wins+1, β=losses+1) updated                           │
│           ↓                                                       │
│  7. When 95% credible interval lower bound > 0.6,                 │
│     promote: INSERT INTO concept_resource_edges                   │
│              (concept, resource_family, domain, weight=0.5)       │
│                                                                   │
│  Curated edges (weight=1.0) always outrank learned edges (0.5).   │
│  Learned edges only win when nothing curated exists.              │
└──────────────────────────────────────────────────────────────────┘
```

### Problem Statement

| Problem | Evidence |
|---------|----------|
| **Graph has blind spots** | FTS5 saves ~15-25% of resolutions where the graph returns empty. These are recurring patterns — the same concept→family gaps appear repeatedly. |
| **No learning from saves** | Every FTS5 save is a one-off rescue. The graph never heals. The same gap will fail again next time. |
| **BM25 can be wrong** | "add apple" could match shopping (apple fruit), health (Apple Watch), or finance (Apple stock). Promoting without evidence poisons the graph. |
| **No negative signal tracking** | When FTS5 suggests capability X but Back selects Y, that's a rejection signal. Currently lost. |

### The Contract

**Never auto-promote.** Every proposed edge must clear a Bayesian confidence gate. The default prior is Beta(1,1) — uniform, 50% mean, infinite variance. You need real evidence to move it.

**Negative signals are as important as positive.** Every time FTS5 suggests X but the system chooses Y, that's a loss for X. Track it.

**Curated edges (weight=1.0) are authoritative.** Learned edges (weight=0.5) are tentative. The `concept_resource_edges` table already has `weight REAL DEFAULT 1.0` and the resolver already uses `ORDER BY weight DESC`. No schema change needed for the ranking — only the promotion logic.

**Promotion requires statistical significance, not a count.** 3-0 sounds confident, but Beta(4,1) has a 95% CI lower bound of 0.40 — too low. You need ~10-1 or 7-0 to cross the 0.6 threshold. The math enforces patience.

### Codebase Reality (What Already Exists)

| Component | File:Line | What's There |
|-----------|-----------|-------------|
| `_source` provenance tag | `capability_type_resolver.py:268` | FTS5 results carry `_source: "fts5"` — tells us when a save happened |
| `concept_resource_edges.weight` | `global_projection_store.py:~255` | `weight REAL DEFAULT 1.0` — curated edges get 1.0, learned get ≤0.5 |
| `get_concept_resource_family()` | `global_projection_store.py:~952` | Already `ORDER BY weight DESC` — learned edges automatically rank below curated |
| `ResolutionEnvelope.verdict` | `situated_resolver.py:85-249` | `can_execute`, `missing_capability`, `needs_hil`, etc. |
| `ResolutionEnvelope.binding_bundle` | `situated_resolver.py` | `primary: CapabilityBinding` — which capability was selected |
| `ResolutionEnvelope.execution_plan` | `situated_resolver.py` | What Back was told to execute |
| `ResolvedIntentType.fallback_capabilities` | `capability_type_resolver.py:98` | `list[dict[str, Any]]` — flows to binder Pass 1 |
| GPS graph ontology tables | `global_projection_store.py:248-298` | `concept_aliases`, `concept_resource_edges`, `resource_connector_edges`, `operation_aliases` — all already have `weight` + `domain` columns |

### GPS Schema — Two New Tables

```sql
-- 5. ONTOLOGY GAP LOG (Phase 2.7, Epic 27.1)
-- Every FTS5 save is logged here.  Rows are upserted: same (concept,
-- family_id, domain_id) tuple increments gap_count + last_seen.
CREATE TABLE IF NOT EXISTS ontology_gaps (
    concept         TEXT NOT NULL,          -- "groceries", "apple"
    family_id       TEXT NOT NULL REFERENCES resource_families(family_id),
    domain_id       TEXT NOT NULL REFERENCES domains(domain_id),
    capability_name TEXT NOT NULL,          -- which capability FTS5 found
    gap_count       INTEGER NOT NULL DEFAULT 1,  -- how many times this gap occurred
    wins            INTEGER NOT NULL DEFAULT 0,  -- execution succeeded
    losses          INTEGER NOT NULL DEFAULT 0,  -- execution failed / overridden
    last_seen       TEXT NOT NULL DEFAULT (datetime('now')),
    promoted        INTEGER NOT NULL DEFAULT 0,  -- 1 after edge created
    PRIMARY KEY (concept, family_id, domain_id)
);

-- 6. RESOLUTION OUTCOME LOG (Phase 2.7, Epic 27.3)
-- Tracks win/loss per resolution for Beta distribution computation.
-- Written post-execution by the orchestration layer.
CREATE TABLE IF NOT EXISTS resolution_outcomes (
    resolution_id   TEXT NOT NULL,
    intent_id       TEXT NOT NULL,
    concept         TEXT NOT NULL,          -- the concept that was tried
    candidate_family_id TEXT NOT NULL,      -- the family FTS5 suggested
    source          TEXT NOT NULL CHECK(source IN ('graph','fts5','rk_hint')),
    outcome         TEXT NOT NULL CHECK(outcome IN ('win','loss','tie')),
    executed_capability TEXT,               -- what Back actually called
    suggested_capability TEXT,              -- what the resolver suggested
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (resolution_id, intent_id, concept, candidate_family_id)
);
```

### Issue 27.1 — Create `ontology_gaps` Table + Gap Logging

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()`, after `connector_resource_families` block
- **DDL:** As above (§5)
- **New method on `GlobalProjectionStore`:**

```python
def upsert_ontology_gap(
    self, concept: str, family_id: str, domain_id: str,
    capability_name: str,
) -> None:
    """Log an FTS5 save — a concept→family mapping the graph missed."""
    self._db.execute(
        """INSERT INTO ontology_gaps (concept, family_id, domain_id,
           capability_name, gap_count, last_seen)
           VALUES (?, ?, ?, ?, 1, datetime('now'))
           ON CONFLICT(concept, family_id, domain_id) DO UPDATE SET
           gap_count = gap_count + 1,
           last_seen = excluded.last_seen""",
        (concept, family_id, domain_id, capability_name),
    )
    self._db.commit()
```

### Issue 27.2 — Wire Gap Logging Into `_resolve_one()`

- **File:** `k1/fabric/resolver/capability_type_resolver.py` — inside the FTS5 fallback block added in Epic 24.1, after FTS5 finds results

**New code (~10 lines, after line ~275):**

```python
                # FTS5 fallback: both graph queries returned empty.
                if not caps and action:
                    fts_results = self.global_store.search_capabilities_by_domain(
                        query=action, domains=[domain] if domain else [], top_k=5)
                    if fts_results:
                        capabilities = [...]
                        evidence.append(...)
                        # ── Self-healing: log the ontology gap ──
                        best = fts_results[0]
                        gap_concept = (
                            concept_hits[0] if concept_hits
                            else rk if rk
                            else action.split()[0] if action
                            else "unknown"
                        )
                        if best.family_id and domain:
                            try:
                                self.global_store.upsert_ontology_gap(
                                    concept=gap_concept,
                                    family_id=best.family_id,
                                    domain_id=domain,
                                    capability_name=best.capability_name,
                                )
                            except Exception:
                                pass  # gap logging is best-effort; never block resolution
```

**Key design decision:** Gap logging is fire-and-forget. If it throws (e.g., GPS not open), the resolution still succeeds. The gap is observational, not critical-path.

### Issue 27.3 — Create `resolution_outcomes` Table + Outcome Logging

- **File:** `k1/fabric/stores/global_projection_store.py` — `_ensure_schema()`
- **DDL:** As above (§6)
- **New method on `GlobalProjectionStore`:**

```python
def log_resolution_outcome(
    self, resolution_id: str, intent_id: str,
    concept: str, candidate_family_id: str,
    source: str, outcome: str,
    executed_capability: str | None = None,
    suggested_capability: str | None = None,
) -> None:
    """Record win/loss after Back executes (or overrides) a capability."""
    self._db.execute(
        """INSERT OR IGNORE INTO resolution_outcomes
           (resolution_id, intent_id, concept, candidate_family_id,
            source, outcome, executed_capability, suggested_capability)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (resolution_id, intent_id, concept, candidate_family_id,
         source, outcome, executed_capability, suggested_capability),
    )
    self._db.commit()
```

### Issue 27.4 — Win/Loss Detector in Orchestration Layer

- **File:** `k1/concierge/actors/back.py` — after `back_handler()` receives the tool execution result, before returning the final envelope

**Logic (~25 lines):**

```python
# After Back executes a tool and gets the result:
# Compute win/loss for each intent that went through resolution.

for intent_resolution in envelope.intent_resolutions:
    suggested_cap = None
    source = "graph"
    for cap in (intent_resolution.fallback_capabilities or []):
        if cap.get("_source") == "fts5":
            source = "fts5"
            suggested_cap = cap.get("capability_name")
            break

    if source == "graph":
        continue  # Only track FTS5 saves — graphs are curated, no learning needed

    executed_cap = execution_result.get("capability_name") if execution_result else None
    execution_ok = execution_result.get("status") == "ok" if execution_result else False
    back_overrode = executed_cap and suggested_cap and executed_cap != suggested_cap
    hil_fired = envelope.verdict == "needs_hil"

    if execution_ok and not back_overrode and not hil_fired:
        outcome = "win"
    elif back_overrode or hil_fired or (execution_result and not execution_ok):
        outcome = "loss"
    else:
        outcome = "tie"

    # Determine the concept that was being resolved
    gap_concept = (
        intent_resolution.resource_family or "unknown"
    )
    candidate_family = (
        envelope.binding_bundle.primary.resource_kind
        if envelope.binding_bundle and envelope.binding_bundle.primary
        else None
    )

    if candidate_family and domain:
        gps.log_resolution_outcome(
            resolution_id=envelope.resolution_id,
            intent_id=intent_resolution.intent_id,
            concept=gap_concept,
            candidate_family_id=candidate_family,
            source=source,
            outcome=outcome,
            executed_capability=executed_cap,
            suggested_capability=suggested_cap,
        )
```

### Issue 27.5 — Beta-Distributed Confidence Computation

- **File:** `k1/fabric/resolver/ontology_learner.py` (NEW)
- **Purpose:** Pure-function module — no side effects, no GPS writes. Just math.

```python
"""OntologyLearner — Bayesian confidence for self-healing graph edges.

Computes Beta-distributed confidence from win/loss counts.
Promotion gate: 95% credible interval lower bound > 0.6.
"""

from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GapConfidence:
    concept: str
    family_id: str
    domain_id: str
    wins: int
    losses: int
    gap_count: int

    @property
    def alpha(self) -> float:
        return self.wins + 1.0  # Beta prior: Beta(1,1)

    @property
    def beta(self) -> float:
        return self.losses + 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def std(self) -> float:
        return math.sqrt(
            (self.alpha * self.beta)
            / ((self.alpha + self.beta) ** 2 * (self.alpha + self.beta + 1))
        )

    @property
    def ci_lower(self) -> float:
        """95% credible interval lower bound (normal approximation)."""
        return max(0.0, self.mean - 1.96 * self.std)

    @property
    def promotable(self) -> bool:
        """Gate: must have ≥3 gaps AND 95% CI lower > 0.6 AND no conflicting
        curated edge with higher weight."""
        return self.gap_count >= 3 and self.ci_lower > 0.6


def compute_gap_confidence(
    wins: int, losses: int, gap_count: int,
    concept: str = "", family_id: str = "", domain_id: str = "",
) -> GapConfidence:
    return GapConfidence(
        concept=concept, family_id=family_id, domain_id=domain_id,
        wins=wins, losses=losses, gap_count=gap_count,
    )
```

**Design note:** This is a pure function. No database access. The GPS methods query `resolution_outcomes` to count wins/losses, then pass the counts to `compute_gap_confidence()`. Separation of concerns: GPS owns data, OntologyLearner owns math.

### Issue 27.6 — Promotion Trigger

- **File:** `k1/fabric/stores/global_projection_store.py` — new method
- **File:** `k1/fabric/resolver/ontology_learner.py` — promotion logic

**New GPS method:**

```python
def promote_ontology_gap(
    self, concept: str, family_id: str, domain_id: str,
) -> bool:
    """Create a learned concept_resource_edges row with weight=0.5.

    Returns True if a new edge was created, False if a curated edge
    already exists (weight >= 1.0) or the gap wasn't found.
    """
    # Check for existing curated edge — never override
    existing = self._db.execute(
        """SELECT weight FROM concept_resource_edges
           WHERE concept = ? AND resource_family = ? AND domain = ?""",
        (concept, family_id, domain_id),
    ).fetchone()
    if existing and existing["weight"] >= 1.0:
        return False  # Curated edge exists — don't touch

    # Upsert learned edge with low weight
    self._db.execute(
        """INSERT INTO concept_resource_edges
           (concept, resource_family, domain, weight)
           VALUES (?, ?, ?, 0.5)
           ON CONFLICT(concept, resource_family, domain) DO UPDATE SET
           weight = 0.5""",
        (concept, family_id, domain_id),
    )
    # Mark gap as promoted
    self._db.execute(
        """UPDATE ontology_gaps SET promoted = 1
           WHERE concept = ? AND family_id = ? AND domain_id = ?""",
        (concept, family_id, domain_id),
    )
    self._db.commit()
    return True
```

**Promotion check (called periodically or at bootstrap):**

```python
def scan_and_promote_gaps(gps: GlobalProjectionStore) -> int:
    """Check all unpromoted gaps. Promote those that clear the Bayesian gate.
    Returns count of promoted edges."""
    from k1.fabric.resolver.ontology_learner import compute_gap_confidence

    gaps = gps._db.execute(
        """SELECT concept, family_id, domain_id, gap_count, wins, losses
           FROM ontology_gaps WHERE promoted = 0"""
    ).fetchall()

    promoted = 0
    for g in gaps:
        conf = compute_gap_confidence(
            wins=g["wins"], losses=g["losses"], gap_count=g["gap_count"],
            concept=g["concept"], family_id=g["family_id"], domain_id=g["domain_id"],
        )
        if conf.promotable:
            if gps.promote_ontology_gap(
                g["concept"], g["family_id"], g["domain_id"]
            ):
                promoted += 1
    return promoted
```

### Issue 27.7 — Update `ontology_gaps` Wins/Losses from Outcomes

- **File:** `k1/fabric/stores/global_projection_store.py` — new method

```python
def sync_gap_outcomes(self) -> int:
    """Aggregate resolution_outcomes into ontology_gaps wins/losses.

    Called periodically.  For each (concept, family_id, domain_id) in
    ontology_gaps, counts wins/losses from resolution_outcomes since
    last sync and updates the gap row.

    Returns count of gaps updated.
    """
    rows = self._db.execute(
        """SELECT concept, candidate_family_id, domain_id,
                  SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                  SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses
           FROM resolution_outcomes
           GROUP BY concept, candidate_family_id, domain_id"""
    ).fetchall()
    count = 0
    for r in rows:
        self._db.execute(
            """UPDATE ontology_gaps
               SET wins = wins + ?, losses = losses + ?
               WHERE concept = ? AND family_id = ? AND domain_id = ?""",
            (r["wins"], r["losses"], r["concept"],
             r["candidate_family_id"], r["domain_id"]),
        )
        count += self._db.total_changes
    self._db.commit()
    return count
```

### Issue 27.8 — Tests

- **GAP-P2-037:** `tests/k1/fabric/resolver/test_ontology_learner.py` (NEW)
- **GAP-P2-037b:** `tests/k1/fabric/stores/test_ontology_gaps.py` (NEW)

| # | Test | What It Proves |
|---|------|---------------|
| 1 | `test_beta_confidence_3_0_not_promotable` | 3 wins, 0 losses → CI lower < 0.6, not promotable |
| 2 | `test_beta_confidence_10_1_is_promotable` | 10 wins, 1 loss → CI lower > 0.6, promotable |
| 3 | `test_beta_confidence_7_0_is_promotable` | 7 wins, 0 losses → CI crosses threshold |
| 4 | `test_beta_confidence_1_5_not_promotable` | 1 win, 5 losses → mean ~0.25, not promotable |
| 5 | `test_beta_confidence_0_0_not_promotable` | No data → Beta(1,1), mean=0.5, CI [0.025, 0.975] |
| 6 | `test_upsert_ontology_gap_increments_count` | Same gap 3 times → gap_count=3 |
| 7 | `test_promote_creates_edge_with_weight_0_5` | Promoted gap → concept_resource_edges row with weight=0.5 |
| 8 | `test_promote_does_not_override_curated_edge` | Existing curated edge (weight=1.0) → promote returns False |
| 9 | `test_log_resolution_outcome_stores_win_loss` | Logged outcome → row in resolution_outcomes |
| 10 | `test_sync_gap_outcomes_aggregates_correctly` | 5 wins + 2 losses in outcomes → ontology_gaps updated |
| 11 | `test_fts5_fallback_logs_gap` | FTS5 saves → ontology_gaps row created/updated |
| 12 | `test_curated_edge_outranks_learned_edge` | Two edges for same concept: weight=1.0 sorts before weight=0.5 |
| 13 | `test_promotion_gate_requires_gap_count_3` | gap_count=2, 10-0 record → NOT promotable (minimum gap_count=3) |
| 14 | `test_scan_and_promote_skips_already_promoted` | promoted=1 gaps are skipped |

- **Run:** `pytest tests/k1/fabric/resolver/test_ontology_learner.py tests/k1/fabric/stores/test_ontology_gaps.py -v`

---

### Files Touched — Exact List

| File | Lines Changed | What |
|------|-------------|------|
| `k1/fabric/stores/global_projection_store.py` | ~60 lines added | 2 new CREATE TABLEs, `upsert_ontology_gap()`, `log_resolution_outcome()`, `promote_ontology_gap()`, `sync_gap_outcomes()`, `scan_and_promote_gaps()` |
| `k1/fabric/resolver/capability_type_resolver.py` | ~10 lines added | Gap logging after FTS5 fallback success |
| `k1/fabric/resolver/ontology_learner.py` | NEW (~60 lines) | `GapConfidence` dataclass, Beta math, `compute_gap_confidence()`, `scan_and_promote_gaps()` |
| `k1/concierge/actors/back.py` | ~25 lines added | Win/loss detection post-execution |
| `tests/k1/fabric/resolver/test_ontology_learner.py` | NEW (8 tests) | Beta confidence math + promotion gate |
| `tests/k1/fabric/stores/test_ontology_gaps.py` | NEW (6 tests) | Gap logging, outcome tracking, sync |

### What This Epic Does NOT Do

- ❌ Does NOT auto-promote — requires Bayesian gate + minimum gap count
- ❌ Does NOT override curated edges (weight=1.0) with learned edges (weight=0.5)
- ❌ Does NOT block resolution on gap logging — fire-and-forget, best-effort
- ❌ Does NOT run promotion at resolution time — promotion is batched/periodic
- ❌ Does NOT use ML embeddings or LLM calls — pure SQL + Beta math, zero GPU
- ❌ Does NOT require new infrastructure — everything is SQLite + Python stdlib `math`

### The Bayesian Gate — Why Beta(1,1)?

| Wins | Losses | α | β | Mean | 95% CI Lower | Promotable? |
|------|--------|---|---|------|-------------|-------------|
| 0 | 0 | 1 | 1 | 0.50 | 0.025 | ❌ (gap_count=0 < 3) |
| 3 | 0 | 4 | 1 | 0.80 | 0.40 | ❌ (CI < 0.6) |
| 5 | 0 | 6 | 1 | 0.86 | 0.55 | ❌ (CI < 0.6) |
| 7 | 0 | 8 | 1 | 0.89 | 0.63 | ✅ |
| 10 | 1 | 11 | 2 | 0.85 | 0.65 | ✅ |
| 3 | 3 | 4 | 4 | 0.50 | 0.15 | ❌ |
| 1 | 5 | 2 | 6 | 0.25 | 0.02 | ❌ |

### Execution Order (Updated)

```
Epic 22 → Epic 23 → Epic 24 → Epic 25 → Epic 26 → Epic 27
(GPS)     (Tools)    (FTS5)    (Prompt)   (Docs)    (Self-Healing)
```

Epic 27 depends on Epics 22 (taxonomy tables), 24 (FTS5 fallback + `_source` tags), and 25 (Back prompt — for outcome detection in back.py). It can be started independently of Epic 26 (docs).

### Summary (Updated)

| Epic | Issues | Files Created | Files Modified | Tests |
|------|--------|--------------|----------------|-------|
| 22 — GPS Schema | 10 | 1 (test) | 4 | 14 |
| 23 — Family Tool Migration | 9 | 1 (test) | 7 | 9 + full regression |
| 24 — Resolver FTS5 | 5 | 1 (test) | 1 | 8 |
| 25 — Back Prompt | 6 | 0 | 2 | 7 |
| 26 — Documentation | 3 | 1 (taxonomy doc) | 2 | Manual review |
| 27 — Self-Healing Ontology | 8 | 3 (learner + 2 tests) | 3 | 14 |
| **Total** | **41** | **7 new files** | **~19 modified** | **~52 new tests** |
