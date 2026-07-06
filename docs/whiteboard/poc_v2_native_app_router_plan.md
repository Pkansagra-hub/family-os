# POC v2: Native-App Router — Milestone Plan

**Status:** PLAN
**Date:** 2026-06-15
**References:** `k1/docs/future_family_apps_development.md`, `scripts/poc_connector_search.py`, review of POC v1
**Branch:** `feature/prompt-architecture-refactor`

---

## Why POC v1 Is Wrong

The architecture redesigned from **connector arbitration** to **native-app routing + backend fan-out**. POC v1 still tests connector arbitration.

| POC v1 Tests | Architecture Requires |
|---|---|
| "Can search find `family.shopping` among 500+ connectors?" | "Given raw utterance + active OS set, which native app?" |
| Competing distractor connectors (chase.*, nest.*, fitbit.*) | Other-OS native apps (health.*, finance.*, pharmaos.*) as distractors |
| LLM-hint based benchmark tiers (EASY/MEDIUM/HARD) | Raw-utterance routing tiers (single-OS, cross-OS, backend-name mention) |
| `expected_connector` always in FamilyOS | `expected_native_app` may be in HealthOS, FinanceOS, PharmaOS, EnterpriseOS |
| No active-OS gating | active_os_set filters visible native apps |
| No backend plane | Backend registry, fan-out, partial failure, dynamic enum injection |
| Schema-augmented = "classifier predicted app X → boost X" | Real manifest compatibility: resource_kind, effect, domain match |
| "87% accuracy" with namespace-prior cheating | Zero-prior accuracy across 5 OS domains |

## What POC v2 Proves

> Given raw user intent + active OS/app surface, route to the correct native app; then pass backend names as arguments, never as tools.

1. **Plane A — Native-App Routing Accuracy:** MiniLM-L6 routes raw utterances to the correct native app across 33 apps in 5 OS domains, with zero namespace prior, at >80% Conn@1.
2. **Plane B — Backend Execution Correctness:** Backend registry, fan-out, partial failure tolerance, dynamic enum injection, and health scoring all work as a separate execution plane below the resolver.

---

## Phase 1: Native-App Routing Benchmark (Plane A)

### Issue PREQ-001: Generate stub native-app definitions for 4 non-FamilyOS domains

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/native_app_stubs.py` |
| **Priority** | BLOCKER — no cross-OS routing without non-FamilyOS apps |
| **Depends on** | Nothing |

**What this does:**

Generate 27 stub native-app connector definitions from the data in `scripts/intent_schema_generator.py` (`DOMAIN_VERTICALS` list) and `k1/docs/future_family_apps_development.md`. Each stub is a minimal GPS-admissible connector definition with:

```python
{
    "connector_id": "health.medications",
    "label": "HealthOS Medications",
    "description": "Prescription management, refill requests, drug interaction checks, vaccine scheduling, and medication reminders across all connected pharmacies.",
    "concept_aliases": ["prescription", "medication", "refill", "dose", "pill", "drug", "pharmacy", "vaccine", "rx"],
    "operation_aliases": ["refill", "renew", "check interactions", "set reminder", "track dose", "compare prices", "request prior auth"],
    "resource_kinds": ["prescription", "medication", "refill", "interaction", "dose", "vaccine"],
    "os_domain": "health",
    "confusable_with": ["health.reminders", "pharmaos.fulfillment", "family.reminders"],
}
```

**Domains and apps:**

| OS Domain | Count | Native Apps |
|-----------|-------|-------------|
| FamilyOS | 6 | calendar, shopping, tasks, reminders, chores, family_settings (already real) |
| HealthOS | 7 | records, appointments, medications, vitals, insurance, caregiving, lab_results |
| FinanceOS | 6 | accounts, budgeting, investing, taxes, insurance, loans |
| PharmaOS | 6 | fulfillment, inventory, insurance, customer, compliance, compounding |
| EnterpriseOS | 8 | hr, payroll, project_mgmt, crm, documentation, communication, devops, it |
| **Total** | **33** | 6 real + 27 stubs |

**Each stub MUST have:**
- `connector_id` — dotted path matching OS domain
- `label` — human-readable name
- `description` — 2-4 sentence paragraph explaining what the native app does, what backends it aggregates
- `concept_aliases` — 10-20 noun phrases users might say (from intent_schema_generator resource_kinds + domain_tags + manual expansion)
- `operation_aliases` — 10-15 verb phrases users might say
- `resource_kinds` — the resource nouns this app owns
- `os_domain` — parent OS domain
- `confusable_with` — other native apps this app is ambiguous with (from intent_schema_generator)

**Source data:**
- `scripts/intent_schema_generator.py` lines 56-450: `DOMAIN_VERTICALS` list with name, os_domain, resource_kinds, domain_tags, confusable_with
- `k1/docs/future_family_apps_development.md`: Full app descriptions with tools, backends, and fan-out patterns

**Verification:**
- All 27 stubs validate against `CONNECTOR_JSON_SCHEMA` (or minimal schema check)
- Each stub's `description` is >100 chars (enough semantic signal for MiniLM)
- Each stub's `concept_aliases` has ≥10 entries
- Each stub's `confusable_with` matches the intent_schema_generator cross-reference
- `python scripts/poc_v2/native_app_stubs.py --validate` passes

---

### Issue PREQ-002: Register all 33 native apps into isolated GPS per benchmark run

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/context_factory.py` |
| **Priority** | BLOCKER — benchmark needs GPS with all native apps |
| **Depends on** | PREQ-001 (stub definitions exist) |

**What this does:**

Replace `poc_connector_search.py`'s `_bootstrap_gps()` with a new context factory that:
1. Creates an in-memory GPS per benchmark run (no cross-contamination)
2. Registers 6 real FamilyOS definitions from `k1.tools.family.*.definition`
3. Registers 27 stub definitions from PREQ-001
4. Builds connector documents (MiniLM embeddings) for all 33 apps
5. Returns `(gps, connector_docs, embedding_index)` for the search variant

**Critical:**
- No synthetic distractors (chase.*, nest.*, fitbit.*, etc.) — those are backends, not native apps
- No namespace prior — OS domain comes from `active_os_set` parameter only
- Each run is isolated — fresh GPS, fresh embeddings

**Verification:**
- `gps.list_connectors()` returns exactly 33 entries
- `embedding_index` has 33 vectors of dimension 384
- No `chase.*`, `nest.*`, `fitbit.*`, or other backend-named connectors in GPS
- Two sequential runs produce identical results (deterministic)

---

### Issue PREQ-003: Write cross-OS benchmark query corpus (~120 queries)

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/bench_queries.py` |
| **Priority** | BLOCKER — what we measure |
| **Depends on** | PREQ-001 (need native app list to write queries against) |

**What this does:**

Write a 120-query benchmark corpus organized into 6 tiers that test the REAL routing challenges:

#### Tier 1: Single-OS FamilyOS (25 queries)
No ambiguity outside FamilyOS. Baseline accuracy.

| Query | Expected Native App | Why |
|-------|---------------------|-----|
| "what's on my calendar this week" | family.calendar | Clear calendar intent |
| "add milk to my grocery list" | family.shopping | Clear shopping intent |
| "remind me to take out the trash tonight" | family.chores | Chore reminder, not generic reminder |
| "did Riley finish her homework" | family.tasks | Task status check |
| "set a reminder to call Mom at 3pm" | family.reminders | Generic time-based reminder |
| "turn off automatic chore rotation" | family.family_settings | Settings toggle |

#### Tier 2: Cross-OS Health vs Family (25 queries)
The REAL ambiguity: is this a family app or a health app?

| Query | Expected Native App | Active OS Set | Why |
|-------|---------------------|---------------|-----|
| "remind me to take my blood pressure medication" | health.medications | {family, health} | Medication reminder, not generic reminder |
| "what time is my doctor appointment tomorrow" | health.appointments | {family, health} | Healthcare appointment, not calendar event |
| "show me my lab results from last week" | health.lab_results | {family, health} | Lab result query |
| "is my blood pressure normal these days" | health.vitals | {family, health} | Vital sign trend |
| "schedule a telehealth visit with Dr. Chen" | health.appointments | {family, health} | Telehealth, not generic calendar |
| "add Metformin to my daily pill reminder" | health.medications | {family, health} | Medication management |
| "I need a refill on my inhaler" | health.medications | {family, health} | Refill request |
| "what vaccinations does Riley need for school" | health.medications | {family, health} | Vaccine schedule |
| "track Mom's blood sugar readings this week" | health.vitals | {family, health} | Vital tracking |
| "find an in-network cardiologist near me" | health.insurance | {family, health} | Insurance provider search |

#### Tier 3: Cross-OS Finance vs Family (20 queries)
Money-related queries that could go to FamilyOS or FinanceOS.

| Query | Expected Native App | Active OS Set | Why |
|-------|---------------------|---------------|-----|
| "we're over budget on groceries this month" | finance.budgeting | {family, finance} | Budget, not shopping |
| "how much did we spend on dining out last month" | finance.budgeting | {family, finance} | Spending analysis |
| "what's our savings goal progress" | finance.budgeting | {family, finance} | Savings tracking |
| "compare mortgage refinance rates" | finance.loans | {family, finance} | Loan management |
| "did my paycheck hit the account yet" | finance.accounts | {family, finance} | Account balance |
| "how are my investments doing this quarter" | finance.investing | {family, finance} | Portfolio check |
| "I need to file my tax return" | finance.taxes | {family, finance} | Tax filing |
| "is our home insurance up for renewal" | finance.insurance | {family, finance} | Insurance, not health insurance |
| "budget $400 for groceries this week" | finance.budgeting | {family, finance} | Budget setting |
| "set aside $200 for Emma's college fund" | finance.investing | {family, finance} | Investment goal |

#### Tier 4: Cross-OS Pharma vs Health vs Family (15 queries)
Pharmacy queries — could be health (medication management), pharma (fulfillment), or family (reminder).

| Query | Expected Native App | Active OS Set | Why |
|-------|---------------------|---------------|-----|
| "Walgreens says my prescription is ready for pickup" | pharmaos.fulfillment | {family, health, pharma} | Fulfillment ready notification |
| "is my Lipitor ready at the pharmacy yet" | pharmaos.fulfillment | {family, health, pharma} | Fulfillment status check |
| "what time does CVS close today" | pharmaos.customer | {family, health, pharma} | Pharmacy customer info |
| "Dr. Chen sent a new prescription to Walgreens" | pharmaos.fulfillment | {family, health, pharma} | Prescription receipt |
| "how much will this prescription cost with my insurance" | pharmaos.insurance | {family, health, pharma} | Insurance adjudication |
| "track my controlled substance inventory" | pharmaos.compliance | {family, health, pharma} | DEA compliance |
| "refill all my active prescriptions" | health.medications | {family, health, pharma} | Medication management (patient-side) |
| "I missed my dose this morning what should I do" | health.medications | {family, health, pharma} | Dose guidance |
| "remind me to pick up my prescription at 5pm" | family.reminders | {family, health, pharma} | Simple time reminder with pharmacy context |
| "check if my amoxicillin interacts with my other meds" | health.medications | {family, health, pharma} | Drug interaction check |

#### Tier 5: EnterpriseOS routing (15 queries)
Work-related queries — distinct from family tasks.

| Query | Expected Native App | Active OS Set | Why |
|-------|---------------------|---------------|-----|
| "request PTO for June 20-24" | enterprise.hr | {enterprise} | Leave request |
| "how many PTO days do I have left" | enterprise.hr | {enterprise} | HR query |
| "deploy the auth service to staging" | enterprise.devops | {enterprise} | Deployment |
| "who's on call this weekend" | enterprise.devops | {enterprise} | On-call schedule |
| "create a ticket for the login bug" | enterprise.project_mgmt | {enterprise} | Ticket creation |
| "what's the status of the Q3 planning epic" | enterprise.project_mgmt | {enterprise} | Project tracking |
| "send the onboarding doc to the new hire" | enterprise.documentation | {enterprise} | Document sharing |
| "message the eng channel about the outage" | enterprise.communication | {enterprise} | Team communication |
| "update the Salesforce deal for Acme Corp" | enterprise.crm | {enterprise} | CRM update |
| "run the Q2 payroll" | enterprise.payroll | {enterprise} | Payroll processing |

#### Tier 6: Backend-name mention — does NOT change routing (20 queries)
User mentions a backend brand name. This is an argument, not a routing decision.

| Query | Expected Native App | Backend Hint (not routed to) | Why |
|-------|---------------------|------------------------------|-----|
| "order milk from Walmart" | family.shopping | walmart-api | Backend name is argument to place_order |
| "add this to my Costco list" | family.shopping | costco-api | Backend brand is list context |
| "compare Kroger vs Aldi prices on eggs" | family.shopping | kroger-api, aldi-api | Price comparison across backends |
| "did my Amazon Fresh order ship yet" | family.shopping | amazon-fresh-api | Order status for specific backend |
| "sync my Todoist tasks to the family board" | family.tasks | todoist | Backend sync, not competing todo app |
| "add this Google Calendar event to family" | family.calendar | google-calendar | Backend source, not destination |
| "my Fitbit says I slept 5 hours" | health.vitals | fitbit | Wearable is data source |
| "log this meal in MyFitnessPal" | health.vitals | myfitnesspal | Nutrition logging through vitals |
| "connect my Venmo to the family account" | finance.accounts | venmo | Payment backend linking |
| "deposit this check with Chase mobile" | finance.accounts | chase | Bank backend, not connector |

**Each query record shape:**

```python
{
    "id": "cross-health-01",
    "utterance": "remind me to take my blood pressure medication",
    "expected_native_app": "health.medications",
    "active_os_set": {"family", "health"},
    "user_role": "family_member",  # or "doctor", "pharmacist", "financial_advisor", etc.
    "tier": "cross_os_health",
    "difficulty_rationale": "medication reminder could route to family.reminders if resolver misses clinical vocabulary",
    "backend_hints": [],  # backend names mentioned in utterance that are NOT routing targets
}
```

**Verification:**
- Exactly 120 queries, no duplicates
- Every `expected_native_app` is one of the 33 registered native apps
- Every `active_os_set` is a subset of {family, health, finance, bank, enterprise, gov, agri, pharma}
- Tier 6 queries all route to native apps, never to backend names
- At least 15 queries per tier for statistical significance
- `python scripts/poc_v2/bench_queries.py --validate` passes

---

### Issue PREQ-004: Implement native-app boundary contracts per app

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/boundary_contracts.py` |
| **Priority** | HIGH — resolver needs a spine, not just cosine similarity |
| **Depends on** | PREQ-001 (need app list) |

**What this does:**

Define a compact manifest per native app that declares what it owns, what it doesn't own, and what it's ambiguous with. This is the resolver's "spine" — used for schema compatibility scoring and cross-app disambiguation.

```python
@dataclass
class NativeAppBoundary:
    native_app: str                    # "health.medications"
    os_domain: str                     # "health"
    owns_resources: list[str]          # ["prescription", "medication", "refill", "dose", "vaccine"]
    owns_effects: list[str]            # ["read", "create", "update", "delete"]
    does_not_own_resources: list[str]  # ["calendar_event", "bank_transaction", "shopping_item"]
    ambiguous_with: dict[str, list[str]]  # {"family.reminders": ["remind me to take my pills", "set a medication alarm"]}
    backend_slots: dict[str, list[str]]   # {"pharmacies": ["cvs", "walgreens", "riteaid"], "pbms": ["express_scripts"]}
    required_os_domains: set[str]      # {"health"} — this app requires HealthOS active
    user_roles: list[str]              # ["patient", "caregiver", "doctor", "pharmacist"] — who can use this
```

**For all 33 native apps.** The data comes from:
- `scripts/intent_schema_generator.py` — `resource_kinds`, `confusable_with`, `os_domain`
- `k1/docs/future_family_apps_development.md` — tool descriptions, backend slots, user classes
- Our own cross-OS benchmark queries (PREQ-003) — ambiguous examples

**Schema compatibility scoring (used in PREQ-006):**

```python
def schema_compatibility(query_resources: set[str], query_effects: set[str], boundary: NativeAppBoundary) -> float:
    """Score how compatible a query's inferred resources/effects are with an app's boundary."""
    resource_overlap = len(query_resources & set(boundary.owns_resources))
    resource_conflict = len(query_resources & set(boundary.does_not_own_resources))
    effect_overlap = len(query_effects & set(boundary.owns_effects))
    if resource_conflict > 0:
        return 0.0  # Hard incompatibility
    return (resource_overlap * 0.6 + effect_overlap * 0.4) / max(len(query_resources | query_effects), 1)
```

**Verification:**
- All 33 apps have boundary contracts
- Every `ambiguous_with` entry references a real native app in the 33
- Every `backend_slots` entry has ≥1 backend example
- `does_not_own_resources` is non-empty for every app (proves the boundary exists)
- `python scripts/poc_v2/boundary_contracts.py --validate` passes

---

### Issue PREQ-005: Implement active-OS gating as first-class router input

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/router.py` (native_app_router function) |
| **Priority** | BLOCKER — without gating, cross-OS routing is wrong |
| **Depends on** | PREQ-002 (GPS), PREQ-003 (queries), PREQ-004 (boundaries) |

**What this does:**

Implement the core routing function that accepts `(raw_utterance, active_os_set)` and returns ranked native apps:

```python
def route_to_native_app(
    utterance: str,
    *,
    active_os_set: set[str],
    connector_docs: list[ConnectorDocument],
    embedding_index: EmbeddingIndex,
    boundaries: dict[str, NativeAppBoundary],
    top_k: int = 5,
) -> list[RoutedApp]:
    """Route raw user utterance to native apps visible in active OS domains."""
    # 1. Gate: only consider apps whose os_domain is in active_os_set
    visible_apps = [
        doc for doc in connector_docs
        if boundaries[doc.connector_id].os_domain in active_os_set
    ]

    # 2. Dense retrieval: MiniLM cosine similarity over gated set
    candidates = embedding_index.search(utterance, candidates=visible_apps, top_k=top_k * 2)

    # 3. Re-rank with schema compatibility (if classifier signals available)
    # 4. Return top-k with scores
```

**active_os_set semantics:**

| User | active_os_set | Rationale |
|------|---------------|-----------|
| Family member | {family} | Only FamilyOS visible |
| Family member with health consent | {family, health} | FamilyOS + HealthOS visible |
| Family member with full stack | {family, health, finance, pharma} | All consumer OSes |
| Doctor | {health} | Only HealthOS visible |
| Pharmacist | {pharma} | Only PharmaOS visible |
| Financial advisor | {finance} | Only FinanceOS visible |
| Bank employee | {bank} | Only BankOS visible |

**Verification:**
- With `active_os_set={family}`, health.* apps get score 0.0 (not in visible set)
- With `active_os_set={family, health}`, "check my blood pressure" routes to health.vitals not family.reminders
- With `active_os_set={enterprise}`, family.* apps get score 0.0
- Gating is applied BEFORE cosine similarity, not as a post-filter

---

### Issue PREQ-006: Implement real schema-augmented search (replace V21's fake schema)

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `scripts/poc_v2/router.py` (schema_scorer module) |
| **Priority** | MEDIUM — V21's fake schema is a known gap, but raw MiniLM may suffice at 33-app scale |
| **Depends on** | PREQ-004 (boundary contracts), PREQ-005 (router) |

**What this does:**

Replace V21's `cid == pred_native_app → boost` with real multi-signal schema compatibility scoring:

```python
def schema_score(candidate: ConnectorDocument, boundary: NativeAppBoundary, query_signals: QuerySignals) -> float:
    """Real schema compatibility — not just 'did classifier predict this app?'."""
    score = 0.0

    # 1. Resource kind compatibility (from classifier or keyword extraction)
    if query_signals.resource_kinds:
        owned = set(boundary.owns_resources)
        not_owned = set(boundary.does_not_own_resources)
        query_resources = set(query_signals.resource_kinds)
        if query_resources & not_owned:
            return 0.0  # Hard veto: query mentions resource this app doesn't own
        score += len(query_resources & owned) / max(len(query_resources), 1) * 0.30

    # 2. Effect compatibility
    if query_signals.effects:
        valid_effects = set(boundary.owns_effects)
        query_effects = set(query_signals.effects)
        score += len(query_effects & valid_effects) / max(len(query_effects), 1) * 0.20

    # 3. Domain match (OS domain in active set — already gated, but double-weight)
    # 4. Concept alias overlap (exact match bonus for query terms in concept_aliases)
    query_tokens = set(tokenize(query_signals.utterance))
    alias_tokens = set(tokenize(" ".join(candidate.concept_aliases)))
    score += len(query_tokens & alias_tokens) / max(len(query_tokens), 1) * 0.25

    # 5. Operation alias overlap
    op_tokens = set(tokenize(" ".join(candidate.operation_aliases)))
    score += len(query_tokens & op_tokens) / max(len(query_tokens), 1) * 0.25

    return score  # 0.0 to 1.0
```

**Key difference from V21:** V21 only boosts the ONE connector whose `cid == classifier_prediction`. This scores ALL candidates on multiple real compatibility dimensions.

**Verification:**
- Query "check my blood pressure" → health.vitals gets high resource_kind score (vital), health.appointments gets low score
- Query "deploy to staging" → enterprise.devops gets high effect score (execute), enterprise.hr gets 0.0 (no execute effect)
- Query "refill my prescription at Walmart" → health.medications and pharmaos.fulfillment both score, decision goes to cosine similarity
- Schema score alone (no cosine) achieves >60% accuracy on Tier 1 queries

---

### Issue PREQ-007: Benchmark runner — Plane A native-app routing

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/bench_native_app_router.py` |
| **Priority** | BLOCKER — this IS the POC |
| **Depends on** | PREQ-002 (GPS), PREQ-003 (queries), PREQ-004 (boundaries), PREQ-005 (router) |

**What this does:**

Replaces `poc_connector_search.py`'s main benchmark loop. Runs the 120 queries through the native-app router and measures:

```
Benchmark: Native-App Router — Plane A
=======================================
33 native apps, 5 OS domains, 120 queries, zero namespace prior

Variant: MiniLM-L6 Raw (V9 equivalent)
──────────────────────────────────────
Tier                        Conn@1   Conn@3   MRR     ms/q
Single-OS Family (25)        XX.X%    XX.X%    .XXX   X.X
Cross-OS Health (25)         XX.X%    XX.X%    .XXX   X.X
Cross-OS Finance (20)        XX.X%    XX.X%    .XXX   X.X
Cross-OS Pharma (15)         XX.X%    XX.X%    .XXX   X.X
EnterpriseOS (15)            XX.X%    XX.X%    .XXX   X.X
Backend-name mention (20)    XX.X%    XX.X%    .XXX   X.X
──────────────────────────────────────
OVERALL (120)                XX.X%    XX.X%    .XXX   X.X

Active-OS Gating Impact:
  Without gating (all 33 apps):  XX.X%
  With gating (active_os_set):   XX.X%  (+X.X)
```

**Variants to run:**
- V9-MiniLM: Raw MiniLM-L6 cosine similarity (our honest baseline)
- V9-MiniLM + schema: Raw MiniLM + real schema compatibility scoring (PREQ-006)
- V9-MiniLM + gating: Raw MiniLM with active-OS gating only
- V9-MiniLM + gating + schema: Full stack — gating + MiniLM + schema
- V9-MiniLM + gating + boundaries: Gating + boundary veto (hard incompatibility = score 0.0)

**Also measures:**
- Leakage: % queries routed to apps outside active_os_set (must be 0.0% with gating)
- Backend-name safety: % of Tier 6 queries where backend name affected routing (must be 0%)
- Per-app accuracy: which native apps are hardest to route to?

**Verification:**
- Runs in <60 seconds for all variants
- Outputs JSON report to `data/poc_v2/native_app_router_report.json`
- Variants are isolated (no shared state)
- Results are deterministic (seed=42)
- `python scripts/poc_v2/bench_native_app_router.py` exits 0

---

### Issue PREQ-008: Compare POC v2 vs POC v1 honestly

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `scripts/poc_v2/bench_native_app_router.py` (report section) |
| **Priority** | HIGH — must show POC v2 is architecturally correct even if raw accuracy looks lower |
| **Depends on** | PREQ-007 (benchmark results) |

**What this does:**

Generate a comparison table showing POC v1 vs POC v2:

| Metric | POC v1 | POC v2 | Delta | Why |
|--------|--------|--------|-------|-----|
| Apps in search space | 6 FamilyOS + 500 fake distractors | 33 native apps across 5 OS domains | N/A | Architecture-correct |
| Conn@1 (honest, no prior) | 85.4% (6 apps) | TBD | TBD | V2 tests harder problem |
| Conn@3 | 96.2% (6 apps) | TBD | TBD | V2 may need alternatives more |
| Cross-OS ambiguity tested? | No | Yes (50 queries) | N/A | V2 tests the REAL dragon |
| Backend-name safety? | Not tested | Yes (20 queries) | N/A | Walmart→argument, not competitor |
| Active-OS gating? | No | Yes | N/A | V1 would route to health.* for family users |
| Namespace prior? | +0.20 family.* (removed) | Zero | N/A | V2 doesn't cheat |
| Distractors correct? | Bank APIs as peer connectors | Other-OS native apps | N/A | V2 architecture is correct |
| Schema scoring real? | cid==pred→boost only | Resource + effect + alias compatibility | N/A | V2 uses real manifest signals |

**The point:** POC v2's raw accuracy number may be LOWER than POC v1's 85.4% because v2 tests a genuinely harder problem (33 apps across 5 domains with cross-OS ambiguity). That's the point — v1's number was inflated by testing the wrong thing. v2's number is honest and architecturally correct.

**Verification:**
- Comparison table included in benchmark report
- Every POC v1 metric footnoted with what was wrong about it

---

## Phase 2: Backend Execution Plane (Plane B)

### Issue PREQ-009: Design backend registry data model

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/backend_registry.py` |
| **Priority** | BLOCKER for Phase 2 — need registry before testing fan-out |
| **Depends on** | Nothing (Phase 2 is parallel to Phase 1) |

**What this does:**

Implement a lightweight backend registry separate from GPS connector registration:

```python
@dataclass
class BackendRegistration:
    backend_id: str                    # "walmart-api"
    native_app: str                    # "family.shopping"
    display_name: str                  # "Walmart"
    auth_type: str                     # "oauth2"
    auth_config: dict                  # {token_url, client_id, scopes}
    endpoints: dict[str, BackendEndpoint]  # tool_name → endpoint config
    rate_limit: RateLimit              # {max_per_min, burst}
    timeout_ms: int                    # 5000
    retry_policy: RetryPolicy          # {max_attempts, backoff}
    health_check_url: str              # "https://api.walmart.com/health"
    schema_mappings: dict[str, SchemaMapper]  # canonical ↔ backend schema
    circuit_breaker: CircuitBreakerConfig

@dataclass
class BackendEndpoint:
    url: str
    method: str                        # GET, POST, etc.
    input_schema_path: str             # path to JSON Schema for backend's expected input
    output_schema_path: str            # path to JSON Schema for backend's output
    rate_limit: RateLimit | None       # per-endpoint override

@dataclass
class BackendHealth:
    backend_id: str
    latency_p50_ms: float
    latency_p99_ms: float
    error_rate_1h: float
    success_rate_24h: float
    last_success: str | None           # ISO timestamp
    consecutive_failures: int
    is_circuit_open: bool

class BackendRegistry:
    """Stores backend registrations, handles connected-backend filtering per user."""

    def get_connected_backends(self, user_id: str, native_app: str) -> list[BackendRegistration]:
        """Which backends has this user connected for this native app?"""

    def get_backend_health(self, backend_id: str) -> BackendHealth:
        """Current health status for a backend."""

    def circuit_break(self, backend_id: str) -> None:
        """Open circuit breaker after consecutive failures."""

    def register_backend(self, registration: BackendRegistration) -> None:
        """Register a new data backend."""
```

**Sample registrations for POC v2:**

| Backend ID | Native App | Type |
|------------|------------|------|
| walmart-api | family.shopping | grocery retailer |
| kroger-api | family.shopping | grocery retailer |
| costco-api | family.shopping | grocery retailer |
| instacart-api | family.shopping | delivery |
| doordash-api | family.shopping | delivery |
| epic-mychart | health.records | EHR |
| cerner-api | health.records | EHR |
| labcorp-api | health.lab_results | lab |
| cvs-api | pharmaos.fulfillment | pharmacy |
| walgreens-api | pharmaos.fulfillment | pharmacy |
| express-scripts | pharmaos.insurance | PBM |
| plaid-api | finance.accounts | banking aggregator |
| ynab-api | finance.budgeting | budgeting |
| turbo-tax-api | finance.taxes | tax filing |

**Verification:**
- Backend registry is separate from GPS — backends are NOT connector documents
- `get_connected_backends("user-1", "family.shopping")` returns only backends user has connected
- Circuit breaker opens after 5 consecutive failures
- Health check data model supports latency, error rate, and success rate

---

### Issue PREQ-010: Implement fan-out execution with partial failure tolerance

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | New: `scripts/poc_v2/fanout_executor.py` |
| **Priority** | BLOCKER for Phase 2 |
| **Depends on** | PREQ-009 (backend registry) |

**What this does:**

Implement the fan-out pattern that every native app uses to query multiple backends in parallel:

```python
@dataclass
class FanOutResult:
    successes: list[Any]
    failures: list[tuple[str, str]]  # (backend_id, error_message)
    total_backends: int
    healthy_backends: int
    is_degraded: bool
    latency_ms: float

async def fan_out_to_backends(
    user_id: str,
    native_app: str,
    operation: str,
    payload: dict,
    registry: BackendRegistry,
) -> FanOutResult:
    """Fan out to all user-connected backends for a native app. Never fails whole call."""

    backends = registry.get_connected_backends(user_id, native_app)

    # Skip circuit-broken backends
    healthy = [b for b in backends if not registry.get_backend_health(b.backend_id).is_circuit_open]

    # Fan out in parallel
    tasks = [_call_backend(b, operation, payload) for b in healthy]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Classify
    successes = []
    failures = []
    for backend, result in zip(healthy, results):
        if isinstance(result, Exception):
            failures.append((backend.backend_id, str(result)))
            registry.record_failure(backend.backend_id)
        else:
            successes.append(result)
            registry.record_success(backend.backend_id)

    return FanOutResult(
        successes=successes,
        failures=failures,
        total_backends=len(backends),
        healthy_backends=len(healthy),
        is_degraded=len(failures) > 0,
        latency_ms=(time.monotonic() - start) * 1000,
    )
```

**Test scenarios:**

1. **All backends healthy:** 5 grocery backends, all return prices → 5 successes, 0 failures
2. **Partial failure:** 3 of 5 backends down → 3 successes, 2 failures, `is_degraded=True`
3. **Circuit breaker:** Backend X fails 5 times → circuit opens → subsequent calls skip X
4. **Timeout:** Backend Y takes 6s, timeout is 5s → marked as failure, other 4 succeed
5. **Empty backends:** User has no connected backends → 0 successes, 0 failures, `is_degraded=False`

**Verification:**
- `fan_out_to_backends` never raises — always returns `FanOutResult`
- Circuit breaker auto-resets after 60s cooldown
- `is_degraded=True` when ≥1 backend fails but ≥1 succeeds
- Backend health metrics update correctly after each call
- `python scripts/poc_v2/fanout_executor.py --test` runs 5 scenarios, all pass

---

### Issue PREQ-011: Implement dynamic enum injection from LPS

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `scripts/poc_v2/dynamic_enum.py` |
| **Priority** | MEDIUM — key architectural proof but less urgent than routing accuracy |
| **Depends on** | PREQ-009 (backend registry) |

**What this does:**

Prove that tool schemas can have their `enum` fields populated dynamically from the user's connected backends at resolution time:

```python
# Static tool schema (stored in GPS):
PLACE_ORDER_SCHEMA = {
    "name": "place_order",
    "parameters": {
        "backend_id": {
            "type": "string",
            "description": "Which backend to place the order with",
            "enum": [],  # ← DYNAMIC — populated at resolution time
        }
    }
}

# At resolution time:
def inject_backend_enums(tool_schemas: list[dict], user_id: str, registry: BackendRegistry) -> list[dict]:
    """Populate dynamic enums from user's connected backends."""
    for schema in tool_schemas:
        for param_name, param in schema["parameters"].items():
            if param.get("enum") == []:  # Dynamic marker
                if param_name == "backend_id":
                    connected = registry.get_connected_backends(user_id, schema["native_app"])
                    param["enum"] = [b.backend_id for b in connected]
                elif param_name == "pharmacy_id":
                    connected = registry.get_connected_backends(user_id, "pharmaos.fulfillment")
                    param["enum"] = [b.backend_id for b in connected]
    return tool_schemas
```

**Test:** User A has Walmart + Kroger connected. User B has Walmart + Costco + Instacart. Same `place_order` schema, different `backend_id` enums per user.

**Verification:**
- User A's envelope: `backend_id.enum = ["walmart-api", "kroger-api"]`
- User B's envelope: `backend_id.enum = ["walmart-api", "costco-api", "instacart-api"]`
- Enum injection happens at resolution time, not at registration time
- No hardcoded backend lists in tool schemas

---

### Issue PREQ-012: Backend health scoring & circuit breaking

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `scripts/poc_v2/backend_health.py` |
| **Priority** | MEDIUM |
| **Depends on** | PREQ-009 (backend registry) |

**What this does:**

Implement per-backend health monitoring:

```python
class BackendHealthTracker:
    def record_success(self, backend_id: str, latency_ms: float) -> None: ...
    def record_failure(self, backend_id: str, error: str) -> None: ...
    def get_health(self, backend_id: str) -> BackendHealth: ...

    @property
    def circuit_breakers(self) -> dict[str, CircuitState]:
        """Backends currently circuit-broken with cooldown remaining."""
```

**Circuit breaker rules:**
- Open after 5 consecutive failures
- Half-open after 60s cooldown (allow 1 probe request)
- Close after 3 consecutive successes in half-open state
- Manual reset available for false positives

**Health scoring:**
- Healthy: error_rate_1h < 5%, latency_p99 < timeout, consecutive_failures < 3
- Degraded: error_rate_1h 5-20%, OR latency_p99 > 0.8 * timeout
- Unhealthy: error_rate_1h > 20%, OR circuit open

**Verification:**
- 5 simulated failures → circuit opens
- 60s wait + 3 successes → circuit closes
- Health status transitions: healthy → degraded → unhealthy → circuit_open → half_open → healthy
- `python scripts/poc_v2/backend_health.py --test` runs state machine test

---

### Issue PREQ-013: Schema normalization — canonical to backend mapper

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `scripts/poc_v2/schema_normalizer.py` |
| **Priority:** | LOW — important for production, not for POC routing benchmark |
| **Depends on** | PREQ-009 (backend registry) |

**What this does:**

Implement the pattern (not all 100+ mappers) showing how each backend's schema normalizes to the canonical schema:

```python
# Canonical schema for a grocery item:
CANONICAL_ITEM = {
    "item_id": str,        # "walmart:123"
    "name": str,           # "Organic Whole Milk"
    "price": float,        # 3.49
    "currency": str,       # "USD"
    "unit": str,           # "gallon"
    "unit_price": float,   # 3.49
    "store": str,          # "Walmart"
    "in_stock": bool,
}

# Walmart → Canonical
def walmart_to_canonical(raw: dict) -> dict:
    return {
        "item_id": f"walmart:{raw['itemId']}",
        "name": raw.get("productName", raw.get("name", "")),
        "price": float(raw.get("price", 0)),
        "currency": raw.get("currency", "USD"),
        "unit": raw.get("unit", "each"),
        "unit_price": float(raw.get("unitPrice", raw.get("price", 0))),
        "store": "Walmart",
        "in_stock": raw.get("availabilityStatus") == "IN_STOCK",
    }

# Kroger → Canonical
def kroger_to_canonical(raw: dict) -> dict:
    return {
        "item_id": f"kroger:{raw['product_id']}",
        "name": raw.get("desc", raw.get("name", "")),
        "price": float(raw.get("current_price", 0)),
        "currency": "USD",
        "unit": raw.get("unit", "each"),
        "unit_price": float(raw.get("current_price", raw.get("price", 0))),
        "store": "Kroger",
        "in_stock": raw.get("inventory_status") != "OUT_OF_STOCK",
    }
```

**Implement 5 mapper pairs** (not all 100+) to prove the pattern:
- walmart-api ↔ canonical
- kroger-api ↔ canonical
- epic-mychart ↔ canonical (patient record)
- cvs-api ↔ canonical (prescription)
- plaid-api ↔ canonical (transaction)

**Verification:**
- Each mapper has a round-trip test: `canonical → backend → canonical` preserves all fields
- Each mapper handles missing/optional fields gracefully
- Normalized output always matches canonical schema

---

## Execution Order

```
Phase 1 (Plane A — Native-App Routing):
  PREQ-001: Generate stub definitions       ← START HERE
  PREQ-002: GPS context factory             ← depends on PREQ-001
  PREQ-003: Cross-OS benchmark queries      ← parallel with PREQ-001/002
  PREQ-004: Boundary contracts              ← depends on PREQ-001
  PREQ-005: Active-OS gating router         ← depends on PREQ-002, PREQ-003, PREQ-004
  PREQ-006: Real schema-augmented search    ← depends on PREQ-004, PREQ-005
  PREQ-007: Benchmark runner                ← depends on PREQ-002 through PREQ-006
  PREQ-008: POC v2 vs v1 comparison         ← depends on PREQ-007

Phase 2 (Plane B — Backend Execution):
  PREQ-009: Backend registry data model     ← parallel to Phase 1
  PREQ-010: Fan-out executor                ← depends on PREQ-009
  PREQ-011: Dynamic enum injection          ← depends on PREQ-009
  PREQ-012: Health scoring & circuit break  ← depends on PREQ-009
  PREQ-013: Schema normalization            ← depends on PREQ-009 (optional)
```

---

## What POC v1 Files Survive

| File | Fate |
|------|------|
| `scripts/poc_connector_search.py` | **Archive** — rename to `scripts/poc_connector_search_v1_archive.py`. The 500 fake distractors are architecturally wrong. |
| `scripts/bench_resolver_search.py` | **Archive** — LLM-hint tiers replaced by raw-utterance tiers. Expected connector format replaced by `expected_native_app` + `active_os_set`. |
| `scripts/intent_schema_generator.py` | **Keep** — `DOMAIN_VERTICALS` is source data for stub definitions and boundary contracts. |
| `scripts/train_intent_classifier.py` | **Keep** — classifier becomes optional Phase 2 component, not essential for 33-app routing. |
| `k1/tools/family/*/definition.py` (6 files) | **Keep** — real FamilyOS definitions registered in POC v2 GPS. |

## What POC v2 Creates

```
scripts/poc_v2/
├── __init__.py
├── README.md                          # How to run POC v2
├── native_app_stubs.py                # PREQ-001: 27 stub definitions
├── context_factory.py                # PREQ-002: GPS + embedding bootstrap
├── bench_queries.py                   # PREQ-003: 120 cross-OS queries
├── boundary_contracts.py              # PREQ-004: 33 native app boundaries
├── router.py                          # PREQ-005: route_to_native_app()
├── schema_scorer.py                   # PREQ-006: real schema compatibility
├── bench_native_app_router.py         # PREQ-007: benchmark runner
├── backend_registry.py                # PREQ-009: backend registration store
├── fanout_executor.py                 # PREQ-010: asyncio.gather fan-out
├── dynamic_enum.py                    # PREQ-011: LPS → schema enum injection
├── backend_health.py                  # PREQ-012: health scoring + circuit breaker
└── schema_normalizer.py               # PREQ-013: canonical ↔ backend mappers

data/poc_v2/
├── native_app_router_report.json      # PREQ-007 output
├── native_app_router_report.md        # PREQ-007 human-readable
└── poc_v1_vs_v2_comparison.md         # PREQ-008 output
```

---

## Success Criteria

1. **Plane A Conn@1 > 80%** across 33 native apps, 5 OS domains, zero namespace prior, with active-OS gating
2. **Cross-OS accuracy > 75%** — the REAL dragon (health.medications vs family.reminders) is tamed
3. **Backend-name safety = 100%** — no query routes to a backend instead of a native app
4. **Active-OS leakage = 0%** — no query routes to an app outside active_os_set
5. **Schema scoring adds ≥+2%** over raw MiniLM (real signal, not fake classifier boost)
6. **Plane B fan-out** handles 5 backends with 3 failing — returns partial results, never throws
7. **Dynamic enum injection** correctly populates backend_id per user's connected backends

---

## Run Commands

```powershell
# Phase 1
python scripts/poc_v2/native_app_stubs.py --validate
python scripts/poc_v2/context_factory.py --validate
python scripts/poc_v2/bench_queries.py --validate
python scripts/poc_v2/boundary_contracts.py --validate
python scripts/poc_v2/bench_native_app_router.py --all-variants

# Phase 2
python scripts/poc_v2/backend_registry.py --validate
python scripts/poc_v2/fanout_executor.py --test
python scripts/poc_v2/dynamic_enum.py --test
python scripts/poc_v2/backend_health.py --test
```
