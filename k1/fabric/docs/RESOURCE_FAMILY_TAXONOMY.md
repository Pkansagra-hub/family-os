# Resource Family Taxonomy — Canonical Reference

> **Status:** Phase 2.6 (GATE-P2.6). Governed by FamilyOS team.
> **Last updated:** 2026-06-10 (Epics 22-25 complete).
> **Audience:** Connector developers (internal + external), kernel contributors, resolver maintainers.
> **Related:** `connector_development_external.md`, `connector_onboarding_familyos.md`, `phase2.6_resource_family_taxonomy_plan.md`.

---

## 0. What This Is

The **Resource Family Taxonomy** is the governed namespace that every connector, capability, and resolver query operates within. It consists of:

| Component | Table | Controlled By | Stability |
|-----------|-------|---------------|-----------|
| **Domains** | `domains` | FamilyOS team | Very stable — new domain = new industry vertical |
| **Resource Families** | `resource_families` | FamilyOS team | Stable — new family when genuinely new real-world category emerges |
| **Domain→Family Mapping** | `domain_resource_families` | FamilyOS team | Evolves with connector ecosystem |
| **Connector→Family Mapping** | `connector_resource_families` | Connector developer | Declared in manifest, FK-validated |

These tables live in `GlobalProjectionStore` (SQLite, `data/global_projection.db`). They are seeded at GPS open time and queried by the resolver, Back prompt builder, and admission pipeline.

---

## 1. Domains (16)

A **domain** is the broadest category. Every connector belongs to exactly one domain. The domain prefix appears in `connector_id` as `{domain}.{connector_name}` (e.g., `family.calendar`, `health.fitbit`).

| Domain ID | Label | Description |
|-----------|-------|-------------|
| `agriculture` | Agriculture & Farming | Crops, livestock, equipment, weather |
| `automotive` | Automotive & Vehicles | Cars, maintenance, registration, insurance |
| `communication` | Messaging & Social | Chat, calls, social media, announcements |
| `education` | Education & Learning | Courses, assignments, grades, degrees |
| `entertainment` | Media & Entertainment | Streaming, gaming, events, subscriptions |
| `family` | Family & Household | Parenting, chores, calendar, shopping, meal planning |
| `finance` | Banking & Finance | Accounts, transactions, budgets, investments, taxes |
| `fitness` | Fitness & Activity | Workouts, tracking, goals, wearables |
| `food` | Food & Cooking | Recipes, meal planning, groceries, restaurants |
| `government` | Government & Civic | Permits, benefits, taxes, voting |
| `health` | Health & Wellness | Medical records, prescriptions, fitness, nutrition |
| `home` | Smart Home & Living | Devices, appliances, security, energy |
| `legal` | Legal & Compliance | Contracts, documents, filings |
| `productivity` | Work & Productivity | Notes, documents, projects, calendars, email |
| `transport` | Transport & Travel | Rides, deliveries, flights, hotels, vehicles |
| `utilities` | Utilities & Services | Electricity, water, gas, internet, waste |

**Adding a new domain:** Rare. Requires FamilyOS team review. A new domain typically means opening a new industry vertical (e.g., `aerospace`, `marine`). Submit a PR adding a row to `_DOMAINS_SEED` in `k1/fabric/stores/global_projection_store.py`.

---

## 2. Resource Families (57)

A **resource family** names a real-world category of things that connectors operate on. It is NOT a connector implementation detail. Multiple connectors in the same domain can share a family. A family can span multiple domains.

### Cross-Domain Families (11)

These appear in many domains. For example, `event` exists in `family` (calendar events), `health` (medical appointments), `education` (class schedules), and `productivity` (meetings).

| Family ID | Label | Description |
|-----------|-------|-------------|
| `contact` | Contacts | People, profiles, relationships, and address book entries |
| `event` | Events | Calendar events, appointments, meetings, and scheduled occurrences |
| `item` | Items | Purchasable or trackable items: groceries, supplies, products |
| `message` | Messages | Chat messages, notifications, announcements, and communications |
| `metric` | Metrics | Measurements, statistics, vital signs, scores, and KPIs |
| `order` | Orders | Purchase orders, service requests, and fulfilment orders |
| `record` | Records | General-purpose records, logs, entries, and filings |
| `reminder` | Reminders | Time-based notification reminders and alerts |
| `setting` | Settings | Configuration, preferences, feature flags, and policy values |
| `subscription` | Subscriptions | Recurring subscriptions, memberships, and service plans |
| `task` | Tasks | To-do items, action items, homework, and completable work units |

### Domain-Specific Families (46)

These are specialized to one or a few domains.

| Family ID | Label | Description |
|-----------|-------|-------------|
| `account` | Accounts | Financial accounts: checking, savings, credit, investment |
| `allergy` | Allergies | Allergy records, reactions, severity, and treatments |
| `assignment` | Assignments | Homework, projects, papers, and graded submissions |
| `benefit` | Benefits | Government benefits, entitlements, social services, and aid |
| `budget` | Budgets | Spending budgets, allocations, and financial plans |
| `certification` | Certifications | Professional certifications, compliance, audits, and attestations |
| `chore` | Chores | Recurring household duties and responsibilities |
| `condition` | Conditions | Medical conditions, diagnoses, chronic issues, and symptoms |
| `course` | Courses | Educational courses, classes, modules, and curricula |
| `credential` | Credentials | Degrees, certificates, licences, and qualifications |
| `delivery` | Deliveries | Package deliveries, shipments, courier services, and tracking |
| `device` | Devices | Smart home devices, appliances, sensors, and IoT endpoints |
| `document` | Documents | Files, documents, attachments, and digital assets |
| `energy` | Energy | Energy usage, electricity, gas, water, and utility consumption |
| `flight` | Flights | Airline flights, itineraries, boarding, and reservations |
| `game` | Games | Games, gaming sessions, achievements, and progress |
| `grade` | Grades | Grades, scores, transcripts, and academic standing |
| `hotel` | Hotels | Hotel bookings, accommodations, check-in, and reservations |
| `immunization` | Immunizations | Vaccination records, immunization schedules, and boosters |
| `insurance` | Insurance | Insurance policies, claims, coverage, and premiums |
| `investment` | Investments | Investment holdings, portfolios, stocks, and funds |
| `invoice` | Invoices | Invoices, bills, receipts, and statements |
| `lab_order` | Lab Orders | Laboratory test orders, results, panels, and imaging |
| `loan` | Loans | Loans, mortgages, debt instruments, and repayment schedules |
| `maintenance` | Maintenance | Equipment maintenance, service schedules, repairs, and upkeep |
| `meal` | Meals | Meals, dining, nutrition intake, and food logging |
| `notification` | Notifications | Push notifications, alerts, reminders, and status updates |
| `payment` | Payments | Payment methods, billing, invoices, and settlement |
| `permit` | Permits | Government permits, licences, applications, and approvals |
| `pet` | Pets | Pet records, veterinary visits, feeding schedules, and care |
| `plant` | Plants | Plants, crops, garden beds, watering, and harvests |
| `playlist` | Playlists | Media playlists, watchlists, queues, and collections |
| `policy` | Policies | Policy documents, rules, terms, agreements, and contracts |
| `prescription` | Prescriptions | Medical prescriptions, medications, dosages, and refills |
| `recipe` | Recipes | Cooking recipes, meal plans, and preparation instructions |
| `report` | Reports | Analytics reports, summaries, dashboards, and exports |
| `reservation` | Reservations | Table bookings, venue reservations, and appointment slots |
| `ride` | Rides | Ride-share trips, taxi journeys, and chauffeur services |
| `security` | Security | Security systems, cameras, locks, alarms, and access control |
| `shipment` | Shipments | Cargo, freight, shipping manifests, and logistics |
| `tax` | Tax | Tax records, filings, deductions, and returns |
| `transaction` | Transactions | Financial transactions, payments, deposits, and transfers |
| `vehicle` | Vehicles | Cars, vehicles, registration, service history, and maintenance |
| `vital` | Vital Signs | Blood pressure, heart rate, temperature, weight, and biometrics |
| `weather` | Weather | Weather forecasts, conditions, alerts, and climate data |
| `workout` | Workouts | Exercise routines, fitness sessions, training plans, and activities |

---

## 3. Domain → Family Mappings

Each domain has a set of valid resource families. A connector in that domain declares which of these families it manages. The Back LLM sees per-domain family lists with descriptions.

| Domain | Count | Families |
|--------|-------|----------|
| `agriculture` | 9 | `device`, `maintenance`, `metric`, `pet`, `plant`, `record`, `report`, `shipment`, `weather` |
| `automotive` | 8 | `certification`, `document`, `insurance`, `maintenance`, `notification`, `record`, `subscription`, `vehicle` |
| `communication` | 6 | `contact`, `event`, `message`, `notification`, `record`, `subscription` |
| `education` | 12 | `assignment`, `certification`, `contact`, `course`, `credential`, `document`, `event`, `grade`, `record`, `report`, `subscription`, `task` |
| `entertainment` | 7 | `event`, `game`, `item`, `order`, `playlist`, `record`, `subscription` |
| `family` | 14 | `chore`, `contact`, `event`, `item`, `meal`, `message`, `notification`, `pet`, `recipe`, `record`, `reminder`, `setting`, `subscription`, `task` |
| `finance` | 15 | `account`, `budget`, `contact`, `insurance`, `investment`, `invoice`, `loan`, `metric`, `payment`, `policy`, `record`, `report`, `subscription`, `tax`, `transaction` |
| `fitness` | 8 | `device`, `event`, `metric`, `notification`, `record`, `report`, `subscription`, `workout` |
| `food` | 7 | `item`, `meal`, `order`, `recipe`, `record`, `reservation`, `subscription` |
| `government` | 7 | `benefit`, `certification`, `document`, `notification`, `permit`, `record`, `tax` |
| `health` | 17 | `allergy`, `certification`, `condition`, `contact`, `document`, `event`, `immunization`, `insurance`, `lab_order`, `meal`, `metric`, `notification`, `prescription`, `record`, `report`, `vital`, `workout` |
| `home` | 10 | `device`, `energy`, `maintenance`, `metric`, `notification`, `record`, `security`, `setting`, `subscription`, `weather` |
| `legal` | 7 | `certification`, `contact`, `document`, `notification`, `policy`, `record`, `subscription` |
| `productivity` | 10 | `contact`, `document`, `event`, `message`, `notification`, `record`, `report`, `setting`, `subscription`, `task` |
| `transport` | 12 | `delivery`, `flight`, `hotel`, `maintenance`, `notification`, `order`, `record`, `reservation`, `ride`, `shipment`, `subscription`, `vehicle` |
| `utilities` | 8 | `energy`, `invoice`, `maintenance`, `metric`, `notification`, `payment`, `record`, `subscription` |

---

## 4. Naming Conventions

### Connector ID

```
{domain_id}.{connector_name}
```

- `domain_id` — MUST match a row in the `domains` table (FK-validated via `connector_resource_families`).
- `connector_name` — lowercase alphanumeric + underscores. Unique within the domain.

Examples: `family.calendar`, `health.fitbit`, `finance.chase`, `education.canvas`.

### Capability Name

```
tool.{invocation_mode}.{domain_id}.{connector_name}.{action_name}
```

- `invocation_mode` — `read` for read-only operations, `execute` for writes/deletes/computes.
- All other segments follow the connector ID convention.

Example: `tool.execute.family.calendar.create_event`.

### Resource Family ID

Lowercase alphanumeric + underscores. Prefer singular nouns (`event`, not `events`). Prefer real-world concepts (`item`, not `shopping_list_entry`).

### How `resource_kind` Relates to `family_id`

`resource_kind` is the LEGACY field on `capabilities`. It still exists for backward compatibility but is deprecated in favor of `family_id`. During migration (Epic 22.6), existing `resource_kind` values were copied to `family_id`. New connectors should set BOTH, with `family_id` matching a row in the `resource_families` table and `resource_kind` as the connector-specific implementation string.

| Concept | Field | Table | Example | Status |
|---------|-------|-------|---------|--------|
| Taxonomy family | `family_id` | `capabilities`, `resource_families` | `event` | ✅ Canonical |
| Connector-specific kind | `resource_kind` | `capabilities` | `calendar_event` | ⚠️ Deprecated |

---

## 5. How the Taxonomy Is Used

### Resolver (Epic 24)

The `CapabilityTypeResolver` uses domain + resource_family to narrow graph queries. When the graph returns empty, FTS5 BM25 search scoped to `c.domain_id` provides a safety net. Results carry `_source: "fts5"` provenance tags.

### Back Prompt (Epic 25)

`_build_registry_hints()` in `KernelService` queries the `domains` and `domain_resource_families` JOIN `resource_families` tables at kernel boot. The returned dict flows through `PortBundle` → `ConciergeRuntime` → `back_handler()` → `build_back_prompt()`. The Back LLM sees:

```
Currently registered domains: Family & Household, Health & Wellness, ...
Registered resource families by domain:
  Family & Household: event (Calendar events and appointments), task (To-do items), ...
  Health & Wellness: prescription (Medical prescriptions), vital (Blood pressure), ...
```

### Connector Bootstrap (Epic 22.8)

`register_definition_to_store()` in `manifest_translator.py` reads `definition.domain_id` and `definition.resource_families` from the `ToolDefinition`. It populates:
- `connectors.domain_id`
- `capabilities.domain_id` + `capabilities.family_id`
- `connector_resource_families` (FK-validated against `resource_families`)

### Admission Pipeline

New connectors must declare `domain_id` and `resource_families` in their `ToolDefinition`. The `connector_resource_families` table enforces FK constraints — a connector cannot declare a family that doesn't exist in the taxonomy.

---

## 6. How to Propose New Taxonomy Entries

### New Domain

1. Check that no existing domain covers your use case.
2. Open a PR against `k1/fabric/stores/global_projection_store.py` adding a row to `_DOMAINS_SEED`.
3. Include: `domain_id` (lowercase, alphanumeric + underscores), `label` (human-readable, title case), `description` (one sentence).
4. Add `domain_resource_families` mappings for at least 3 families relevant to the domain.
5. FamilyOS team reviews. Approval criteria: genuinely new industry vertical, at least one real connector planned.

### New Resource Family

1. Check the existing 57 families — is there one that already covers the concept?
2. Open a PR adding a row to `_RESOURCE_FAMILIES_SEED`.
3. Include: `family_id`, `label`, `description`.
4. Add `domain_resource_families` mappings linking the family to all relevant domains.
5. FamilyOS team reviews. Approval criteria: real-world concept not already covered, cross-domain applicability preferred.

### New Domain→Family Mapping

1. Open a PR adding a row to `_DOMAIN_RESOURCE_FAMILIES_SEED`.
2. Both `domain_id` and `family_id` must already exist in their respective tables.
3. FamilyOS team reviews. Approval criteria: makes semantic sense for the domain.

---

## 7. Migration from Pre-Phase-2.6 GPS

If you have a `global_projection.db` created before Phase 2.6 (Epic 22):

1. **Automatic:** `_ensure_schema()` runs `ALTER TABLE connectors ADD COLUMN domain_id` and `ALTER TABLE capabilities ADD COLUMN domain_id, family_id`.
2. **Automatic:** Migration UPDATE populates `domain_id` from `connector_id` prefix and `family_id` from `resource_kind`.
3. **Manual (if needed):** `resource_kind` values like `"calendar_event"` are connector-specific strings. Review them against the `resource_families` table and update `family_id` to canonical values (e.g., `"calendar_event"` → `"event"`) if desired. The old `resource_kind` column is preserved.

No data loss. No DROP COLUMN. Both `resource_kind` and `family_id` coexist.

---

## 8. Programmatic Access

```python
from k1.fabric.stores.global_projection_store import GlobalProjectionStore

gps = GlobalProjectionStore("data/global_projection.db")
gps.open()

# All domains
domains = gps.get_domains()  # ["agriculture", "automotive", ...]

# Families for a domain
families = gps.get_resource_families_for_domain("family")
# [{"family_id": "event", "label": "Events", "description": "Calendar events..."}, ...]

# Families for a connector
connector_families = gps.get_connector_resource_families("family.calendar")
# ["event"]

# FTS5 search scoped to domain
results = gps.search_capabilities_by_domain("schedule appointment", ["family"], top_k=5)
```

---

## 9. Related Files

| File | Purpose |
|------|---------|
| `k1/fabric/stores/global_projection_store.py` | Schema + seed data (`_DOMAINS_SEED`, `_RESOURCE_FAMILIES_SEED`, `_DOMAIN_RESOURCE_FAMILIES_SEED`) |
| `k1/fabric/manifest_translator.py` | Populates `connector_resource_families` at bootstrap |
| `k1/kernel/service.py` | `_build_registry_hints()` queries taxonomy for Back prompt |
| `k1/concierge/prompt/back_prompt.py` | `build_back_prompt()` renders per-domain grouped narrative |
| `k1/fabric/resolver/capability_type_resolver.py` | 3-tier resolution: graph → domain-agnostic → FTS5 BM25 |
| `k1/tools/family/definition.py` | `ToolDefinition` fields: `domain_id`, `resource_families`, `resource_kinds` |
| `k1/fabric/docs/phase2.6_resource_family_taxonomy_plan.md` | Full implementation plan (Epics 22-27) |
