# Future Family Apps Development — The Native-App-as-Aggregator Architecture

**Status:** Architecture Design
**Date:** 2026-06-13
**Principle:** The Back LLM sees only native apps. External services are backends, not peers.

---

## Table of Contents

1. [Core Architecture Principle](#core-architecture-principle)
2. [Two Kinds of Connectors](#two-kinds-of-connectors)
3. [The 8-Domain Family](#the-8-domain-family)
4. [Domain 1: FamilyOS — Household Operating System](#domain-1-familyos--household-operating-system)
5. [Domain 2: HealthOS — Healthcare Operating System](#domain-2-healthos--healthcare-operating-system)
6. [Domain 3: FinanceOS — Personal Finance Operating System](#domain-3-financeos--personal-finance-operating-system)
7. [Domain 4: BankOS — Banking Infrastructure OS](#domain-4-bankos--banking-infrastructure-os)
8. [Domain 5: EnterpriseOS — Business Operations OS](#domain-5-enterpriseos--business-operations-os)
9. [Domain 6: GovOS — Government Services OS](#domain-6-govos--government-services-os)
10. [Domain 7: AgriOS — Agricultural Operations OS](#domain-7-agrios--agricultural-operations-os)
11. [Domain 8: PharmaOS — Pharmacy Operations OS](#domain-8-pharmaos--pharmacy-operations-os)
12. [Cross-OS Event Architecture](#cross-os-event-architecture)
13. [The Two-Layer App Architecture — Every OS Follows the Same Pattern](#the-two-layer-app-architecture--every-os-follows-the-same-pattern)
14. [Cross-Cutting Architecture Patterns](#cross-cutting-architecture-patterns)
15. [Implications for Connector Search](#implications-for-connector-search)
16. [Migration Impact on Resolver Redesign](#migration-impact-on-resolver-redesign)

---

## Core Architecture Principle

```
                     USER
                      │
                      ▼
              ┌───────────────┐
              │   Back LLM    │  ← sees ONLY native-domain apps as tools
              │               │     (6 per domain × 7 domains = ~42 tools)
              └───────┬───────┘
                      │ "price_check: milk, eggs, bread"
                      ▼
              ┌───────────────────────┐
              │  family.shopping       │  ← THE shopping app. The only one.
              │  (native domain app)   │
              │                       │
              │  ┌─────────────────┐  │
              │  │ price_check     │  │  ← one tool, not 20 competing ones
              │  │ place_order     │  │
              │  │ list_items      │  │
              │  │ compare_prices  │  │
              │  │ track_spending  │  │
              │  └────────┬────────┘  │
              └───────────┼───────────┘
                          │ fans out to N backends in parallel
              ┌───────────┼───────────┬───────────┬───────────┐
              ▼           ▼           ▼           ▼           ▼
          ┌──────┐  ┌─────────┐  ┌───────┐  ┌──────────┐  ┌──────┐
          │Walmart│  │Costco   │  │Kroger │  │Instacart │  │Target│  ...
          │ API  │  │ API     │  │ API   │  │ API      │  │ API  │
          └──────┘  └─────────┘  └───────┘  └──────────┘  └──────┘
              │           │           │           │           │
              └───────────┴───────────┴───────────┴───────────┘
                                  │ aggregate
                                  ▼
              ┌───────────────────────────────────────┐
              │  Price Comparison                     │
              │  ┌──────────┬────────┬────────┬─────┐ │
              │  │ Walmart  │ $3.49  │ 1.2mi  │ ★★★ │ │
              │  │ Costco   │ $3.29  │ 3.8mi  │ ★★☆ │ │
              │  │ Kroger   │ $3.79  │ 0.4mi  │ ★★★ │ │
              │  │ Instacart│ $4.19  │ N/A    │ ★★☆ │ │
              │  └──────────┴────────┴────────┴─────┘ │
              └───────────────────────────────────────┘
```

### Fundamental Rule

> **External services are backends data feeds to native apps, not peer tool providers competing for the Back LLM's attention.**

The Back LLM never calls Walmart's API. It never calls Instacart's API. It never calls a competitor's API. It calls `family.shopping.price_check`, and the native app handles everything downstream.

---

### Split-Order Flow: Multi-Backend Order Placement

The user doesn't have to pick ONE store. They can split an order across backends.

```
    User: "Order 4 items from Costco and 3 from Walmart"
                      │
                      ▼
              ┌───────────────────────────────────────────┐
              │              Back LLM                     │
              │                                          │
              │  Sees price comparison from earlier turn   │
              │  Decides optimal split:                   │
              │    Costco:  milk, eggs, bread, cheese     │
              │    Walmart: paper towels, detergent, bags │
              │                                          │
              │  Makes TWO tool calls in ONE turn:        │
              │                                          │
              │  ┌────────────────────────────────────┐  │
              │  │ place_order(                       │  │
              │  │   backend_id="costco-api",         │  │
              │  │   items=["milk","eggs","bread",    │  │
              │  │           "cheese"],              │  │
              │  │   delivery="home"                  │  │
              │  │ )                                  │  │
              │  └────────────────────────────────────┘  │
              │                                          │
              │  ┌────────────────────────────────────┐  │
              │  │ place_order(                       │  │
              │  │   backend_id="walmart-api",        │  │
              │  │   items=["paper towels",           │  │
              │  │           "detergent","trash bags"],│  │
              │  │   delivery="home"                  │  │
              │  │ )                                  │  │
              │  └────────────────────────────────────┘  │
              └──────────┬─────────────┬─────────────────┘
                         │             │
              ┌──────────┼─────────────┼─────────────┐
              │          ▼             ▼             │
              │   ┌───────────┐ ┌───────────┐        │
              │   │  Costco   │ │  Walmart  │        │
              │   │  API      │ │  API      │        │
              │   │           │ │           │        │
              │   │ Order #1  │ │ Order #2  │        │
              │   │ 4 items   │ │ 3 items   │        │
              │   │ $23.96    │ │ $18.47    │        │
              │   └───────────┘ └───────────┘        │
              │                                      │
              │    family.shopping (native app)       │
              │    routes each call to the correct    │
              │    backend based on backend_id        │
              └──────────────────────────────────────┘
                         │             │
                         └──────┬──────┘
                                ▼
              ┌───────────────────────────────────────┐
              │  Order Confirmation                   │
              │  ┌──────────┬──────────┬────────────┐ │
              │  │ Costco   │ $23.96   │ #C-48291   │ │
              │  │ Walmart  │ $18.47   │ #W-73921   │ │
              │  ├──────────┼──────────┼────────────┤ │
              │  │ TOTAL    │ $42.43   │ 2 orders   │ │
              │  └──────────┴──────────┴────────────┘ │
              └───────────────────────────────────────┘
```

#### How the Back LLM Knows Which Backend to Use

The `place_order` tool signature includes `backend_id`:

```json
{
  "name": "place_order",
  "description": "Place an order on a specific backend. Call once per backend for split orders.",
  "parameters": {
    "backend_id": {
      "type": "string",
      "description": "Which connected backend to place the order with. Get valid IDs from price_check results.",
      "enum": ["dynamic — populated from user's connected backends"]
    },
    "items": {
      "type": "array",
      "items": { "type": "object", "properties": {
        "name": { "type": "string" },
        "quantity": { "type": "integer" }
      }}
    },
    "delivery": {
      "type": "string",
      "enum": ["home", "pickup", "curbside"]
    }
  }
}
```

#### The Three Order Scenarios

| Scenario | User Says | Back LLM Does |
|----------|-----------|---------------|
| **Single-backend** | "Order everything from Costco" | 1 call: `place_order(backend_id="costco-api", items=[...])` |
| **User-specified split** | "4 from Costco, 3 from Walmart" | 2 calls: `place_order(backend_id="costco-api", items=[...4...])` + `place_order(backend_id="walmart-api", items=[...3...])` |
| **Cheapest overall** | "Order from wherever is cheapest" | LLM runs `price_check`, analyzes results, computes optimal split, then N calls |

#### Cheapest-Overall Optimization

```python
# The Back LLM calls price_check, gets this back:
comparison = {
    "milk":    {"walmart": 3.49, "costco": 3.29, "kroger": 3.79},
    "eggs":    {"walmart": 4.99, "costco": 5.49, "kroger": 4.49},
    "bread":   {"walmart": 2.99, "costco": 2.49, "kroger": 3.29},
    "cheese":  {"walmart": 5.99, "costco": 4.99, "kroger": 6.49},
}

# The LLM reasons: "Costco is cheaper on 3 of 4 items. One Costco order beats
# splitting across stores when factoring $9.99 delivery fee per order."
# → 1 call: place_order(backend_id="costco-api", items=[all 4])

# But if the user says "order 30 items," the LLM computes:
# Costco all-30: $142.30 + $9.99 delivery = $152.29
# Walmart 15 + Costco 15: $68.40 + $71.20 + $9.99×2 = $159.58
# → 1 call: place_order(backend_id="costco-api", items=[all 30])
```

#### Why This Isn't a Race Condition

Each `place_order` call is **independent and idempotent**. They go to different backends. They don't share state. The native app is the transaction coordinator:

```
place_order(Costco, [milk, eggs])          place_order(Walmart, [towels, bags])
         │                                            │
         ▼                                            ▼
    Costco API                                    Walmart API
    Creates order #C-48291                        Creates order #W-73921
    Returns confirmation                          Returns confirmation
         │                                            │
         └──────────────┬─────────────────────────────┘
                        ▼
              family.shopping aggregates:
              {
                "orders": [
                  {"backend": "costco-api", "order_id": "C-48291", "total": 23.96},
                  {"backend": "walmart-api", "order_id": "W-73921", "total": 18.47}
                ],
                "grand_total": 42.43,
                "all_succeeded": true
              }
```

If Costco succeeds but Walmart fails (API down), the user sees one confirmed order and one failed order — NOT a corrupted half-state. Each backend order is atomic.

---

## Two Kinds of Connectors

| Property | Native Domain App | Data Backend |
|----------|-------------------|--------------|
| **Registered in GPS?** | Yes — full admission manifest | Yes — config-only registration |
| **Visible to Back LLM?** | **YES** — these are the tools | **NO** — never exposed as tools |
| **Has callable tools?** | Yes — the Back LLM calls these | No — the native app calls these |
| **Exposes tool schemas?** | Yes — JSON Schema for each tool | No — internal API contract only |
| **Count per domain** | ~4-8 native apps | ~20-200+ backend connectors |
| **Who writes them?** | FamilyOS platform team | Third-party developers or native-app team |
| **Admission scope** | Full: constitution, policy, tools, schema | Lightweight: endpoint URL, auth, rate limits, schema mapping |
| **Example** | `family.shopping` | `walmart-api`, `kroger-api` |

### Data Backend Registration (Lightweight)

```yaml
# walmart-api.backend.yaml — NOT a full connector, just a backend config
backend_id: "walmart-api"
native_app: "family.shopping"
auth:
  type: "oauth2"
  token_url: "https://api.walmart.com/oauth2/token"
endpoints:
  price_check:
    url: "https://api.walmart.com/v3/items/prices"
    method: POST
    input_schema: "walmart_price_request.json"   # native app normalizes TO this
    output_schema: "walmart_price_response.json" # native app normalizes FROM this
    rate_limit: 100/min
  place_order:
    url: "https://api.walmart.com/v3/orders"
    method: POST
    input_schema: "walmart_order_request.json"
    output_schema: "walmart_order_response.json"
    rate_limit: 20/min
health_check: "https://api.walmart.com/health"
timeout_ms: 5000
retry: { max_attempts: 3, backoff: "exponential" }
```

---

## The 8-Domain Family

Each domain follows the EXACT same architecture. The pattern scales horizontally.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FAMILY OF OPERATING SYSTEMS                    │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │FamilyOS  │ │HealthOS  │ │FinanceOS │ │ BankOS   │ │Enterprise│  │
│  │          │ │          │ │          │ │          │ │    OS    │  │
│  │Household │ │Doctors & │ │Financial │ │Banks &   │ │Business  │  │
│  │Life      │ │Hospitals │ │Advisors  │ │Fintech   │ │Operations│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                              │
│  │  GovOS   │ │  AgriOS  │ │ PharmaOS │                              │
│  │          │ │          │ │          │                              │
│  │Government│ │Farming & │ │Pharmacies│                              │
│  │Services  │ │Food Chain│ │& Med Mgmt│                              │
│  └──────────┘ └──────────┘ └──────────┘                              │
│                                                                      │
│  Each domain: 4-8 native apps, 20-200 data backends per app          │
│  Total scale: ~50 native apps, ~600-2500+ data backends              │
│                                                                      │
│  Each OS is SOVEREIGN — they share EVENTS at borders, not data.      │
│  ONE Back LLM. ONE GPS. ONE resolver. ONE constitution framework.    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Domain 1: FamilyOS — Household Operating System

**Users:** Families, parents, children, caregivers
**Native Apps:** 6
**Estimated Data Backends:** ~50-200 per user

### Native Apps & Their Data Backends

#### 1. family.shopping — Household Shopping Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `price_check` | Check prices across all connected grocery/delivery services | Walmart, Costco, Kroger, Instacart, Target, Safeway, Whole Foods, ALDI, Trader Joe's, Publix, Wegmans, HEB, Amazon Fresh, DoorDash, Uber Eats, Grubhub |
| `place_order` | Place order on selected backend after user confirms | Any of the above |
| `list_items` | View/manage shopping items across all lists | Aggregated view across all backends |
| `compare_prices` | Side-by-side price comparison with unit pricing | All connected backends |
| `track_spending` | Spending analytics across all grocery purchases | Aggregated from order histories |
| `stock_alerts` | Low-stock and price-drop alerts | All connected backends |

**Fan-Out Pattern:**

```python
async def price_check(items: list[str], user_id: str) -> PriceComparison:
    backends = await get_user_backends(user_id, app="family.shopping")
    # Fan out to all connected backends in parallel
    results = await asyncio.gather(*[
        backend.search_prices(items, zip_code=user.zip_code)
        for backend in backends
    ], return_exceptions=True)
    # Aggregate, sort by price, annotate with distance/store info
    return PriceComparison(
        items=items,
        results=sorted(
            [r for r in results if not isinstance(r, Exception)],
            key=lambda r: r.unit_price
        ),
        partial_failures=[r for r in results if isinstance(r, Exception)]
    )
```

---

#### 2. family.calendar — Family Calendar Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `create_event` | Create event synced across all calendars | Google Calendar, Outlook, Apple Calendar, CalDAV servers |
| `check_schedule` | Check availability across all calendars | All connected calendar providers |
| `find_free_slot` | Find open time across all family members | All members' calendars |
| `sync_event` | Two-way sync of event changes | All connected providers |

---

#### 3. family.tasks — Family Task Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `create_task` | Create task, sync to preferred backend | Todoist, TickTick, Microsoft To Do, Any.do, Trello, Asana, ClickUp, Things, OmniFocus |
| `mark_done` | Mark complete, sync everywhere | All connected task backends |
| `assign_to` | Assign to family member | Native + sync to backend |
| `list_tasks` | Unified task view across all backends | Aggregated from all |

---

#### 4. family.reminders — Unified Reminder System

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `set_reminder` | Set reminder, sync to preferred app | Due, Apple Reminders, Google Keep, MediSafe, WaterMinder, Bring, Binge Clock |
| `dismiss_reminder` | Dismiss across all | All connected |
| `snooze_reminder` | Snooze with custom interval | All connected |
| `list_reminders` | Unified reminder dashboard | Aggregated from all |

---

#### 5. family.chores — Household Chore Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `complete_chore` | Complete chore instance | Tody, Sweepy, OurHome, Chorsee, Nipto, Maple, FlyLady |
| `assign_chore` | Assign to family member with rotation | Native scheduling + backend sync |
| `list_chores` | Unified chore dashboard | Aggregated from all |
| `set_schedule` | Configure recurring chore schedule | Native + sync |

---

#### 6. family.family_settings — Family Configuration

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `toggle_feature` | Enable/disable family features | Native only (no external backends) |
| `set_permission` | Manage family member permissions | Native only |
| `manage_accounts` | Connect/disconnect external accounts | Account linking UI |

---

## Domain 2: HealthOS — Healthcare Operating System

**Users:** Patients, caregivers, hospitals, clinics, insurers
**Native Apps:** 7
**Estimated Data Backends:** ~50-300 per institution

### Native Apps & Their Data Backends

#### 1. health.records — Unified Health Records

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_patient_history` | Aggregate full patient history | Epic MyChart, Cerner HealtheLife, AthenaHealth, Allscripts, Meditech, Apple Health Records, hospital patient portals, VA Health |
| `reconcile_medications` | Cross-reference medications across providers | All connected EHRs, pharmacy records |
| `get_lab_results` | Aggregate labs across labs and providers | LabCorp, Quest Diagnostics, BioReference, hospital labs, at-home test kits |
| `get_immunizations` | Pull immunization records | State registries, provider EHRs, school records |
| `get_allergies` | Aggregate allergy data across providers | All connected EHRs |
| `get_imaging` | Pull radiology reports and images | Hospital PACS systems, imaging centers |
| `emergency_profile` | Generate emergency-ready patient summary | Aggregated from all sources |

**Critical Design Constraint:** HIPAA compliance. All PHI stays within the native app's encrypted boundary. Backend connectors never see each other's data. Aggregation happens in the native app's secure enclave — not in the Back LLM context.

```
┌─────────────────────────────────────────────────────┐
│                 health.records                       │
│  ┌───────────────────────────────────────────────┐  │
│  │           SECURE AGGREGATION ENCLAVE           │  │
│  │                                               │  │
│  │  Epic ◄─────► [Normalize] ◄─┐                 │  │
│  │  Cerner ◄───► [Normalize] ◄─┤                 │  │
│  │  LabCorp ◄──► [Normalize] ◄─┼─► Unified View  │  │
│  │  Quest ◄────► [Normalize] ◄─┤                 │  │
│  │  Apple H. ◄─► [Normalize] ◄─┘                 │  │
│  │                                               │  │
│  │  Back LLM sees ONLY unified view,             │  │
│  │  NEVER raw EHR data or backend connectors     │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

#### 2. health.appointments — Appointment Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `find_provider` | Search across networks by specialty, location, insurance | ZocDoc, hospital networks, clinic portals, insurance provider directories |
| `book_appointment` | Book across any connected provider system | All connected scheduling systems |
| `check_availability` | Real-time slot check across providers | All connected |
| `telehealth_join` | Join telehealth visit regardless of platform | Zoom Healthcare, Doxy.me, Epic Telehealth, Amwell, Teladoc |
| `schedule_followup` | Schedule follow-up with preferred provider | All connected |

---

#### 3. health.medications — Medication Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `list_prescriptions` | Aggregate active prescriptions | CVS, Walgreens, Rite Aid, Capsule, Alto, hospital pharmacies, mail-order |
| `check_interactions` | Cross-reference for drug interactions | Drugs.com API, FDA database, Epocrates, Micromedex |
| `refill_request` | Request refill from any pharmacy | All connected pharmacies |
| `price_compare` | Compare cash price, insurance, and GoodRx | GoodRx, SingleCare, RxSaver, pharmacy APIs |
| `medication_reminder` | Set reminders with dose tracking | MediSafe, Round Health, Pill Reminder, native reminders |
| `vaccine_schedule` | Track and schedule vaccinations | CDC schedule, state registries, pharmacy appointments |

---

#### 4. health.vitals — Vitals & Wellness Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_vitals` | Aggregate latest vitals from wearables | Fitbit, Apple Health, Garmin, Oura, Whoop, Withings, Samsung Health |
| `get_trends` | Long-term trend analysis across devices | All connected wearables |
| `get_sleep_data` | Unified sleep analysis | All connected devices |
| `get_activity_data` | Unified activity and exercise data | All connected devices + Strava, Peloton |
| `set_health_goal` | Set goal synced across platforms | Native + sync to connected platforms |

---

#### 5. health.insurance — Insurance Navigator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `check_coverage` | Check if procedure/medication is covered | Aetna, UnitedHealth, Blue Cross, Cigna, Humana, Medicare, Medicaid |
| `estimate_cost` | Estimate out-of-pocket cost | Insurance APIs + provider pricing |
| `find_in_network` | Find in-network providers | All connected insurance plans |
| `file_claim` | Submit claim to correct insurer | All connected plans |
| `track_deductible` | Track deductible and OOP max across plans | All connected plans |
| `appeal_denial` | Generate and submit appeal documentation | Insurance-specific workflows |

---

#### 6. health.caregiving — Caregiver Coordination

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `care_plan` | Create and manage care plan across providers | All connected provider systems |
| `care_team_chat` | HIPAA-compliant messaging between caregivers | Native secure messaging |
| `share_records` | Share specific records with authorized caregivers | Role-based access controls |
| `emergency_contacts` | Manage emergency contacts and ICE info | Native + sync to EHR |
| `track_adl` | Track Activities of Daily Living | Caregiver check-in apps, sensor data |

---

#### 7. health.lab_results — Lab Result Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_results` | Pull results from all labs | LabCorp, Quest, BioReference, hospital labs |
| `interpret_results` | Plain-language interpretation with reference ranges | Aggregated from lab reports |
| `trend_labs` | Track lab values over time | All historical results |
| `share_with_provider` | Securely share results with designated providers | Direct secure messaging |
| `schedule_lab` | Find and schedule lab draw appointments | Lab location APIs |

---

## Domain 3: FinanceOS — Personal Finance Operating System

**Users:** Individuals, families, financial advisors
**Native Apps:** 6
**Estimated Data Backends:** ~100-500 per user

### Native Apps & Their Data Backends

#### 1. finance.accounts — Unified Financial Accounts

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_all_balances` | Aggregate balances across all accounts | Chase, BofA, Wells Fargo, Citi, US Bank, Capital One, credit unions, Venmo, PayPal, Cash App, Apple Cash |
| `get_transactions` | Unified transaction feed across accounts | All connected (via Plaid, Yodlee, or direct API) |
| `transfer_funds` | Transfer between connected accounts | All connected bank APIs |
| `categorize_spending` | Auto-categorize transactions across accounts | Native ML + user rules |
| `net_worth` | Real-time net worth calculation | All connected accounts + investments + debts |

**Security Model:**

```
┌─────────────────────────────────────────────────┐
│              finance.accounts                    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │         READ-ONLY AGGREGATION            │    │
│  │  (Back LLM can READ balances,            │    │
│  │   transactions, categories.             │    │
│  │   It CANNOT initiate transfers           │    │
│  │   without explicit user confirmation.)  │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │         WRITE-GATED OPERATIONS           │    │
│  │  (HITL confirmation required for:        │    │
│  │   - transfers > $threshold               │    │
│  │   - new external account linking         │    │
│  │   - changing security settings)          │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

---

#### 2. finance.investments — Investment Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_portfolio` | Aggregate portfolio across all brokerages | Robinhood, Fidelity, Vanguard, Schwab, E*TRADE, Webull, M1 Finance, Betterment, Wealthfront, Acorns |
| `get_performance` | Time-weighted return across all accounts | All connected brokerages |
| `asset_allocation` | Unified asset allocation view | Cross-account aggregation |
| `tax_loss_harvest` | Identify TLH opportunities across accounts | All connected |
| `get_crypto_portfolio` | Aggregate crypto holdings | Coinbase, Binance, Kraken, Gemini, MetaMask, Ledger |
| `rebalance_check` | Check portfolio drift from target allocation | All connected |

---

#### 3. finance.budget — Budget Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `create_budget` | Create budget synced to preferred app | Mint, YNAB, EveryDollar, Copilot, Monarch, Simplifi |
| `track_spending` | Real-time spending vs budget across categories | Aggregated from all connected accounts |
| `forecast_cashflow` | Project future balances based on recurring bills | All connected accounts + bill APIs |
| `savings_goals` | Track progress toward savings goals | Aggregated across accounts and apps |
| `bill_negotiation` | Identify bills that can be negotiated down | Billshark, Trim, Rocket Money |

---

#### 4. finance.taxes — Tax Preparation Aggregator

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `gather_documents` | Aggregate W-2s, 1099s, 1098s, etc. | Employer portals, brokerages, banks, mortgage servicers |
| `estimate_tax` | Real-time estimated tax calculation | Tax engine + all connected financial data |
| `find_deductions` | Identify missed deductions across all accounts | Cross-account analysis |
| `file_return` | Prepare and file with preferred provider | TurboTax, H&R Block, TaxAct, FreeTaxUSA, CPA portal |
| `track_refund` | Track refund status | IRS Where's My Refund + state equivalents |

---

#### 5. finance.loans — Loan Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_all_loans` | Aggregate all loans across servicers | Mortgage servicers, student loan servicers (Nelnet, FedLoan, Aidvantage), auto lenders, personal loan providers |
| `compare_refinance` | Check refinance rates across lenders | LendingTree, Credible, SoFi, banks, credit unions |
| `payoff_forecast` | Project payoff dates with extra payments | All connected loans |
| `forbearance_check` | Check eligibility for deferment/forbearance | All connected servicers |

---

#### 6. finance.insurance — Personal Insurance Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `get_policies` | Aggregate all insurance policies | GEICO, Progressive, State Farm, Allstate, Lemonade, Hippo, MetLife |
| `compare_quotes` | Compare insurance quotes across providers | Policygenius, Zebra, Insurify + direct APIs |
| `file_claim` | File claim with correct insurer | All connected insurers |
| `renewal_check` | Check upcoming renewals and rate changes | All connected policies |
| `bundle_analysis` | Identify bundling opportunities across insurers | Cross-policy analysis |

---

## Domain 4: BankOS — Banking Infrastructure OS

**Users:** Banks, credit unions, fintech companies (B2B)
**This is NOT a consumer product — it's bank infrastructure software.**
**Native Apps:** 6
**Estimated Data Backends:** ~50-200 per institution

### Native Apps & Their Data Backends

#### 1. bankos.customers — Customer 360

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `customer_profile` | Aggregate customer data across systems | Salesforce Financial Cloud, HubSpot, core banking system, CRM |
| `kyc_verify` | Run KYC verification across providers | Alloy, Jumio, Onfido, Trulioo, Socure, ID.me |
| `risk_assessment` | Composite customer risk score | Multiple risk models + bureau data |
| `onboarding_status` | Track onboarding completion across steps | All connected onboarding systems |
| `customer_communications` | Unified communication history | Email, SMS, push, in-app, branch visits, call center |

---

#### 2. bankos.transactions — Payment Processing Hub

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `route_payment` | Route payment through optimal rail | FedWire, SWIFT, ACH, RTP, FedNow, SEPA, card networks |
| `fx_rate` | Compare FX rates across liquidity providers | Multiple FX providers, interbank rates |
| `settlement_status` | Track settlement across clearing systems | All connected payment rails |
| `reconciliation` | Auto-reconcile across payment systems | All transaction systems |
| `payment_analytics` | Cross-rail payment performance analytics | Aggregated from all rails |

---

#### 3. bankos.compliance — Regulatory Compliance Hub

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `aml_screening` | Screen against sanctions and watchlists | OFAC, UN, EU, UK sanctions lists; World-Check, LexisNexis |
| `transaction_monitoring` | Real-time AML transaction monitoring | Multiple AML engines |
| `regulatory_reporting` | Generate regulatory filings | Fed, FDIC, OCC, CFPB, FinCEN, state regulators |
| `audit_trail` | Unified audit trail across all systems | All connected banking systems |
| `policy_attestation` | Track policy compliance attestations | Compliance management systems |

---

#### 4. bankos.lending — Loan Origination & Servicing

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `credit_check` | Pull and aggregate credit data | Experian, Equifax, TransUnion, Innovis, ChexSystems |
| `underwriting_assessment` | Composite underwriting decision | Multiple UW models + bureau data + income verification |
| `loan_portfolio` | Aggregate loan portfolio across systems | All lending systems |
| `collections_status` | Unified collections view | All collection systems |
| `loss_mitigation` | Identify and track loss mitigation options | All servicing systems |

---

#### 5. bankos.fraud — Fraud Detection & Prevention

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `fraud_score` | Composite fraud score across vendors | Feedzai, DataVisor, Kount, Sift, Featurespace, ComplyAdvantage |
| `device_fingerprint` | Aggregate device intelligence | ThreatMetrix, LexisNexis, iovation, Fingerprint |
| `behavioral_biometrics` | Aggregate behavioral signals | BioCatch, BehavioSec, NuData |
| `case_management` | Unified fraud case across systems | All fraud systems |
| `fraud_network` | Share/consume fraud intelligence | Consortium data sharing |

---

#### 6. bankos.treasury — Treasury Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `cash_position` | Aggregate cash position across accounts | All correspondent banks, Federal Reserve, Nostro/Vostro accounts |
| `liquidity_forecast` | Multi-horizon liquidity forecasting | All treasury systems |
| `fx_exposure` | Aggregate FX exposure across currencies | All FX trading systems |
| `funding_optimization` | Optimize funding across sources | Fed Funds, repo, commercial paper, interbank |
| `collateral_management` | Aggregate collateral positions | All collateral systems |

---

## Domain 5: EnterpriseOS — Business Operations OS

**Users:** Companies (SMB to Enterprise), department heads, employees
**Native Apps:** 8
**Estimated Data Backends:** ~100-1000+ per enterprise

### Native Apps & Their Data Backends

#### 1. enterprise.communication — Unified Communications

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `send_message` | Send message, route to optimal channel | Slack, Teams, Discord, WhatsApp Business, Telegram, Signal |
| `search_all` | Full-text search across all comms platforms | All connected platforms |
| `schedule_meeting` | Schedule with room/video availability check | Google Calendar, Outlook, Zoom, Teams, Webex |
| `unified_inbox` | Aggregated inbox across email + chat | Gmail, Outlook, Slack, Teams |
| `presence_status` | Aggregated presence across platforms | All connected |

---

#### 2. enterprise.hr — Human Resources Hub

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `employee_profile` | Unified employee record | Workday, BambooHR, Gusto, ADP, Rippling, SAP SuccessFactors |
| `payroll_summary` | Aggregate payroll data | ADP, Gusto, Rippling, Paychex, QuickBooks Payroll |
| `benefits_enrollment` | Cross-platform benefits management | All connected benefits platforms |
| `performance_review` | Aggregate performance data | Lattice, 15Five, Culture Amp, Workday |
| `recruiting_pipeline` | Aggregate recruiting across platforms | Greenhouse, Lever, Ashby, LinkedIn Recruiter, Indeed |
| `time_off` | Unified PTO calendar | All connected HR systems |
| `compliance_training` | Track training completion across platforms | All LMS platforms |

---

#### 3. enterprise.finance — Corporate Finance

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `financial_close` | Aggregate financial data for close | NetSuite, SAP, Oracle, QuickBooks, Xero, Sage |
| `expense_management` | Aggregate expenses across systems | Concur, Expensify, Ramp, Brex, Divvy |
| `invoicing` | Aggregate AR/AP across systems | Bill.com, Stripe Invoicing, QuickBooks, NetSuite |
| `budget_vs_actual` | Cross-system budget tracking | ERP + FP&A tools (Adaptive, Anaplan, Planful) |
| `revenue_analytics` | Aggregate revenue across products/channels | Stripe, Chargebee, Recurly, Salesforce |

---

#### 4. enterprise.crm — Customer Relationship Hub

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `customer_360` | Aggregate customer data across all touchpoints | Salesforce, HubSpot, Zoho, Pipedrive, Freshsales, Intercom, Zendesk |
| `pipeline_view` | Unified pipeline across sales teams | All CRM systems |
| `customer_health` | Composite customer health score | CRM + support tickets + product usage + billing |
| `renewal_forecast` | Predict renewals across accounts | Aggregated from all systems |
| `churn_risk` | Identify at-risk accounts | Cross-system analysis |

---

#### 5. enterprise.devops — Developer Operations

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `incident_response` | Aggregate alerts, create unified incident | PagerDuty, OpsGenie, Datadog, Sentry, Grafana, CloudWatch |
| `deployment_status` | Track deployments across services | GitHub Actions, GitLab CI, CircleCI, Jenkins, ArgoCD, Spinnaker |
| `infrastructure_view` | Aggregate infra across clouds | AWS, GCP, Azure, k8s clusters, Terraform Cloud |
| `cost_optimization` | Cross-cloud cost analysis | AWS Cost Explorer, GCP Billing, Azure Cost Mgmt, CloudAbility |
| `on_call_schedule` | Unified on-call across teams | PagerDuty, OpsGenie, VictorOps |

---

#### 6. enterprise.legal — Legal Operations

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `contract_repository` | Search across all contract systems | Ironclad, LinkSquares, DocuSign CLM, SpringCM, Conga |
| `contract_review` | AI-assisted review across platforms | All connected contract systems |
| `compliance_check` | Cross-reference against regulatory requirements | All regulatory feeds |
| `litigation_tracker` | Aggregate litigation across matters | All matter management systems |
| `ip_portfolio` | Aggregate IP assets (patents, trademarks) | IP management systems |

---

#### 7. enterprise.marketing — Marketing Operations

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `campaign_performance` | Aggregate campaign data across channels | Google Ads, Meta Ads, LinkedIn Ads, TikTok Ads, email platforms (HubSpot, Marketo, Mailchimp) |
| `customer_journey` | Cross-channel customer journey mapping | All marketing + sales + support systems |
| `content_calendar` | Unified content calendar across platforms | All CMS + social media scheduling tools |
| `roi_attribution` | Multi-touch attribution across channels | Aggregated from all marketing systems |
| `competitor_intel` | Aggregate competitive intelligence | Crayon, Klue, Kompyte, social listening |

---

#### 8. enterprise.it — IT Service Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `ticket_view` | Aggregate IT tickets across systems | ServiceNow, Jira Service Management, Zendesk, Freshservice, Ivanti |
| `asset_inventory` | Aggregate hardware/software assets | All asset management systems |
| `access_review` | Aggregate access across all systems | Okta, Azure AD, JumpCloud, Duo, SailPoint |
| `security_alerts` | Aggregate security alerts | CrowdStrike, SentinelOne, Splunk, Palo Alto, Wiz |
| `change_management` | CAB — aggregate change requests | All ITSM systems |

---

## Domain 6: GovOS — Government Services OS

**Users:** Citizens, government employees, agencies
**Native Apps:** 6
**Estimated Data Backends:** ~50-500 per jurisdiction

### Native Apps & Their Data Backends

#### 1. govos.citizen_services — Citizen Service Hub

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `my_case_status` | Check status across all government cases | USCIS, SSA, VA, IRS, State Department, DMV, local permits |
| `find_benefits` | Discover eligible benefits across programs | SNAP, WIC, Medicaid, Medicare, unemployment, housing assistance, LIHEAP, TANF |
| `apply_benefits` | Unified benefits application | All connected benefit programs |
| `schedule_appointment` | Book appointments across agencies | DMV, SSA, passport, USCIS biometrics |
| `vital_records` | Request birth/death/marriage certificates | State vital records offices |
| `notify_me` | Set alerts for case status changes | All connected agencies |

**Design Constraint:** GovOS must handle the widest diversity of backend quality — from modern REST APIs (USCIS) to screen-scraped mainframe terminals (some county systems).

```
┌──────────────────────────────────────────────────────────┐
│              govos.citizen_services                       │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │          BACKEND QUALITY SPECTRUM                 │    │
│  │                                                  │    │
│  │  Tier 1: Modern REST API (USCIS, SSA, IRS)       │    │
│  │  Tier 2: SOAP/XML web services (state DMVs)      │    │
│  │  Tier 3: Legacy mainframe (county courts)        │    │
│  │  Tier 4: Paper-only (some small counties)        │    │
│  │                                                  │    │
│  │  ← Native app normalizes ALL to unified JSON    │    │
│  │  ← Tier 4 queues human-in-loop case worker       │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

#### 2. govos.permitting — Permitting & Licensing

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `check_requirements` | Aggregate permit requirements | Building department, zoning, environmental, health department, fire marshal |
| `submit_permit` | Submit and track across departments | All connected permitting systems |
| `inspection_status` | Track inspections across agencies | All inspection systems |
| `business_license` | Aggregate licensing requirements | Federal, state, county, city |
| `environmental_review` | Track environmental impact review | EPA, state environmental agencies, Army Corps |

---

#### 3. govos.benefits — Benefits Administration

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `eligibility_screener` | Cross-program eligibility check | All benefit programs |
| `benefit_calculation` | Calculate estimated benefits across programs | All benefit engines |
| `recertification` | Handle recertification across programs | All connected programs |
| `fraud_prevention` | Cross-program fraud detection | All benefit systems |
| `payment_tracking` | Track benefit payments across programs | Treasury + state disbursement systems |

---

#### 4. govos.tax — Tax Administration

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `file_return` | File across jurisdictions | IRS, state revenue departments, local tax authorities |
| `check_refund` | Track refunds across jurisdictions | IRS Where's My Refund, state equivalents |
| `payment_plan` | Manage payment plans across jurisdictions | All tax authorities |
| `audit_support` | Aggregate documents for audit response | All financial systems |
| `estimated_tax` | Calculate estimated taxes across jurisdictions | Multi-jurisdiction tax engine |

---

#### 5. govos.public_safety — Public Safety Coordination

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `emergency_alerts` | Aggregate and disseminate emergency alerts | FEMA IPAWS, NOAA weather, AMBER alerts, local alert systems |
| `incident_report` | File and track police/fire/EMS reports | All public safety systems |
| `evacuation_routes` | Aggregate real-time evacuation information | DOT, emergency management, transit agencies |
| `shelter_locator` | Find open emergency shelters | Red Cross, FEMA, local emergency management |
| `disaster_assistance` | Apply for disaster assistance | FEMA, SBA, insurance |

---

#### 6. govos.infrastructure — Infrastructure Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `road_conditions` | Aggregate road conditions and closures | DOT, Waze, 511 systems, weather services |
| `transit_status` | Aggregate transit across agencies | All transit agencies (bus, train, subway, ferry) |
| `utility_outages` | Aggregate outage information | Power, water, gas, internet providers |
| `waste_collection` | Aggregate waste management schedules | Sanitation departments, private haulers |
| `capital_projects` | Track infrastructure projects | All public works departments |

---

## Domain 7: AgriOS — Agricultural Operations OS

**Users:** Farmers, ranchers, agribusiness, food processors, distributors
**Native Apps:** 6
**Estimated Data Backends:** ~50-300 per operation

### Native Apps & Their Data Backends

#### 1. agrios.crops — Crop Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `field_health` | Aggregate crop health data | John Deere Ops Center, Climate FieldView, Trimble Ag, satellite imagery (Planet, Sentinel), drone imagery |
| `soil_analysis` | Aggregate soil test results | Local extension offices, commercial labs, on-field sensors |
| `planting_recommendation` | Generate planting plan across data sources | Seed suppliers, weather data, soil data, market prices |
| `yield_prediction` | Predict yield across fields | Historical data + real-time conditions across all sources |
| `pest_disease_alert` | Aggregate pest and disease warnings | Extension services, sensor networks, neighboring farm reports |
| `irrigation_schedule` | Optimize irrigation across fields | CropX, soil moisture sensors, weather forecasts, water rights data |

**Scale Challenge:** A single farm may have 50+ fields, each with soil sensors, irrigation controllers, and drone imagery. The native app aggregates across all of them.

```
┌──────────────────────────────────────────────────────┐
│                  agrios.crops                         │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │          FIELD-LEVEL AGGREGATION              │    │
│  │                                              │    │
│  │  Field A ┌─► JD Ops Center                   │    │
│  │          ├─► Climate FieldView               │    │
│  │          ├─► CropX moisture sensors (x12)    │    │
│  │          └─► Planet satellite (weekly image) │    │
│  │                                              │    │
│  │  Field B ┌─► JD Ops Center                   │    │
│  │          └─► Drone imagery (daily)           │    │
│  │                                              │    │
│  │  ... 50+ fields ...                         │    │
│  │                                              │    │
│  │  Cross-field: ┌─► Weather stations (x5)     │    │
│  │               ├─► Market price feeds         │    │
│  │               └─► USDA reports               │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

---

#### 2. agrios.livestock — Livestock Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `herd_health` | Aggregate health data per animal/group | RFID ear tags, collars (Allflex, Cowlar), veterinary records, feed intake monitors |
| `breeding_schedule` | Manage breeding across herd | Genetic databases, herd management software, vet schedules |
| `milk_production` | Aggregate milk production data | Parlor management systems (DeLaval, GEA, Lely), quality testing labs |
| `weight_tracking` | Track weight gain across animals | Weighing systems, feed efficiency calculators |
| `animal_movement` | Track animal location and movement | GPS collars, virtual fencing systems |

---

#### 3. agrios.market — Agricultural Market Intelligence

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `commodity_prices` | Aggregate live commodity prices | CME Group, USDA AMS, local elevators, futures markets |
| `contract_pricing` | Compare contract prices from buyers | All connected buyers and processors |
| `price_forecast` | Generate price forecasts from multiple models | USDA WASDE, private analysts, futures curves |
| `find_buyer` | Search for buyers offering best prices | All connected marketplaces |
| `sell_crop` | List and sell crop/harvest | All connected marketplaces and direct buyers |
| `input_prices` | Compare input costs (seed, fertilizer, chemical) | All suppliers |

---

#### 4. agrios.equipment — Equipment Management

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `fleet_status` | Aggregate status across all equipment | John Deere, Case IH, New Holland, Kubota telematics; all GPS trackers |
| `maintenance_schedule` | Unified maintenance calendar | All equipment telematics + service records |
| `fuel_consumption` | Aggregate fuel usage across fleet | All equipment + fuel storage monitors |
| `utilization_report` | Which equipment is under/over utilized? | Cross-fleet analysis |
| `service_request` | Request service from dealers | All connected dealer service APIs |
| `downtime_cost` | Calculate cost of equipment downtime | Aggregated from operational data |

---

#### 5. agrios.weather — Agricultural Weather Intelligence

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `field_forecast` | Per-field hyperlocal forecast | NOAA, Weather.com, AccuWeather, on-farm weather stations, DTN, Weather Underground |
| `growing_degree_days` | Calculate GDDs across fields | Aggregated from all weather sources + field data |
| `frost_risk` | Frost warning with field-specific risk | All weather sources + field elevation/topography |
| `precipitation_tracking` | Aggregate rainfall across fields | On-farm rain gauges, radar estimates, satellite |
| `drought_monitor` | Track drought conditions | US Drought Monitor, soil moisture, reservoir levels |

---

#### 6. agrios.supply_chain — Agricultural Supply Chain

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `inventory_status` | Aggregate inventory across storage | Grain bins, cold storage, warehouses |
| `logistics_planning` | Coordinate transportation | Trucking companies, rail, barge, port schedules |
| `quality_tracking` | Aggregate quality/grading data | Lab results, inspector reports, buyer specifications |
| `traceability` | End-to-end traceability from field to plate | All supply chain participants |
| `certification_status` | Track organic, non-GMO, fair trade certs | All certifying bodies |
| `sustainability_reporting` | Generate sustainability metrics | Aggregated from all operational data |

---

## Domain 8: PharmaOS — Pharmacy Operations OS

**Users:** Pharmacists, pharmacy technicians, pharmacy chains, fulfillment centers
**Native Apps:** 6
**Estimated Data Backends:** ~10-50 per pharmacy

### Native Apps & Their Data Backends

#### 1. pharmaos.fulfillment — Prescription Fulfillment

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `receive_prescription` | Receive and validate e-prescriptions | SureScripts, EPCS, provider EHRs |
| `verify_medication` | Drug utilization review, interaction check | Micromedex, Lexicomp, Epocrates, FDA |
| `fill_prescription` | Fill, label, and prepare for dispensing | Pharmacy automation (ScriptPro, Parata, Omnicell) |
| `pharmacist_review` | Final check before dispensing | Workflow queues, pharmacist stations |
| `patient_pickup` | Verify identity, counsel, complete sale | POS systems, signature capture |
| `delivery_queue` | Manage home delivery and mail-order | Delivery logistics, cold chain |

---

#### 2. pharmaos.inventory — Inventory & Supply Chain

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `stock_levels` | Real-time inventory across locations | Wholesalers (McKesson, Cardinal, AmerisourceBergen), direct manufacturers |
| `auto_reorder` | Automatic reorder based on par levels | All connected wholesalers |
| `cold_chain_monitor` | Temperature monitoring for biologics/vaccines | IoT sensors, compliance logs |
| `drug_recall` | Recall management and lot tracking | FDA, manufacturers, wholesalers |
| `controlled_substance` | DEA Schedule II-V tracking | DEA CSOS, state PDMP systems |
| `returns_processing` | Process expired/returned medications | Reverse distributors |

---

#### 3. pharmaos.insurance — Insurance Adjudication

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `adjudicate_claim` | Real-time claim adjudication | PBMs (Express Scripts, CVS Caremark, OptumRx), insurance payers |
| `prior_authorization` | Submit and track prior auth requests | All connected payers |
| `copay_calculation` | Calculate patient copay/coinsurance | PBM formularies, insurance plans |
| `coupon_application` | Apply manufacturer coupons and discount cards | GoodRx, SingleCare, manufacturer programs |
| `medicare_part_d` | Medicare Part D compliance and billing | CMS, Medicare plans |

---

#### 4. pharmaos.customer — Patient Communication

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `ready_notification` | Notify patient prescription is ready | SMS, push notification, email, IVR |
| `pickup_reminder` | Remind patient to pick up before return | All communication channels |
| `refill_reminder` | Proactive refill reminders | Sync with fulfillment schedule |
| `counseling_notes` | Pharmacist counseling documentation | Internal records |
| `satisfaction_survey` | Post-pickup satisfaction and adherence check | Survey platforms |

---

#### 5. pharmaos.compliance — Regulatory Compliance

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `dea_tracking` | Controlled substance inventory and dispensing logs | DEA CSOS, ARCOS |
| `hipaa_audit` | HIPAA audit trail for all PHI access | Audit log systems |
| `board_compliance` | State board of pharmacy compliance | State BOP systems |
| `usp_797_800` | Sterile and hazardous compounding compliance | Environmental monitoring, testing |
| `medication_error` | Error reporting and root cause analysis | Internal + ISMP reporting |

---

#### 6. pharmaos.compounding — Compounding Pharmacy

| Tool | Description | Backends Fan-Out |
|------|-------------|------------------|
| `formula_management` | Manage compounding formulas and recipes | USP, professional references |
| `batch_tracking` | Track compound batches by lot and expiration | Internal inventory |
| `quality_testing` | Schedule and track potency/sterility testing | Third-party testing labs |
| `custom_packaging` | Special packaging for compliance packaging | Packaging suppliers |

---

## Cross-OS Event Architecture

### Information Sovereignty by Architecture

> **Each OS is sovereign. They don't share data. They share events.**

A prescription doesn't cross the OS boundary as raw FHIR data. It crosses as a
domain event with exactly the fields the emitting OS chooses to publish:

```
HealthOS → IFL event: prescription.issued {
    patient_familyos_id: "emma-smith-family-8a3f",
    medication: "Lisinopril 20mg",
    dosage: "1 tablet daily",
    quantity: 30,
    refills: 3,
    prescribing_doctor: "Dr. Sarah Chen, MD",
    issued_at: "2026-06-13T09:30:00Z",
    pharmacy_preferred: "walgreens-preston-rd"
}
```

FamilyOS receives this. It doesn't have the doctor's clinical notes. It doesn't
have the diagnosis code. It doesn't even have access to HealthOS. It has
exactly what HealthOS chose to emit — and nothing more.

The pharmacy receives the order event, not the patient's health record. The
pharmacy sees: "Lisinopril 20mg, quantity 30, patient pickup at 1:00 PM."
Not "Emma has hypertension with Stage 2 CKD."

**Three sovereign domains. Three different data views of the same underlying
reality. Zero shared databases. Events only at borders.**

---

### User Classes Per OS

Each OS has its **own primary user class**. They're not all facing the same person.
FamilyOS is the only consumer-facing OS. Every other OS serves professionals.

| OS | Primary User Class | Role in the Network |
|----|-------------------|---------------------|
| **FamilyOS** | Families, parents, kids, caregivers | **Consumer** — receives events, makes life decisions |
| **HealthOS** | Doctors, nurses, hospitals, clinics | **Provider** — creates clinical events |
| **FinanceOS** | Financial planners, CPAs, wealth advisors | **Advisor** — creates financial plan events |
| **BankOS** | Bank employees, compliance officers, tellers | **Institution** — processes, verifies, clears |
| **EnterpriseOS** | HR, managers, IT, employees | **Employer** — creates life-change events |
| **GovOS** | Case workers, agency staff, citizens | **Government** — creates benefit/status events |
| **AgriOS** | Farmers, ranchers, supply chain managers | **Producer** — creates harvest/market events |
| **PharmaOS** | Pharmacists, pharmacy techs, fulfillment | **Fulfillment** — fills prescriptions, emits pickup events |

These are **professional operating systems** for professional users. A financial
planner runs FinanceOS. Their client's family runs FamilyOS. The two talk via
events at the border. Provider-to-consumer. Institution-to-household.

---

### FamilyOS: The Terminal Consumer Node

```
                    ┌──────────────────────────────┐
                    │     PROFESSIONAL LAYER        │
                    │                              │
    HealthOS ───────┤  Doctors prescribe           │
    FinanceOS ──────┤  Advisors plan               │──┐
    BankOS ─────────┤  Banks process               │  │
    EnterpriseOS ───┤  Employers manage             │  │  All emit
    GovOS ──────────┤  Government administers       │  │  events
    AgriOS ─────────┤  Farmers produce              │  │  downward
    PharmaOS ───────┤  Pharmacists fulfill          │──┘
                    │                              │
                    └──────────────────────────────┘
                                    │
                           IFL event bus
                                    │
                    ┌───────────────┴──────────────┐
                    │      FAMILYOS                │
                    │                              │
                    │  The ONLY consumer-facing OS  │
                    │                              │
                    │  Receives events.             │
                    │  Translates to life actions.  │
                    │  Shopping, calendar, tasks,   │
                    │  reminders, chores.           │
                    │                              │
                    │  Every professional OS        │
                    │  touches a family somewhere.  │
                    │  FamilyOS is where it lands.  │
                    └──────────────────────────────┘
```

FamilyOS isn't "one of eight." It's the **human terminal** of the entire
professional infrastructure network. Every doctor, every banker, every employer,
every government agency — they all eventually produce events that affect
someone's family. FamilyOS is where those events become actionable in daily life.

---

### Cross-OS Event Flow Table (Bi-Directional)

Events flow in **both directions**. Professional OSes emit events that land in
FamilyOS. FamilyOS emits events that feed back into professional OSes. The loop
closes.

```
SOURCE OS       EVENT                       TARGET OS       WHAT HAPPENS
─────────       ─────                       ─────────       ────────────
HealthOS        prescription.issued          FamilyOS        "New prescription, fill it?"
HealthOS        diagnosis.issued             FinanceOS       Financial planner: plan for long-term care costs
HealthOS        appointment.scheduled        FamilyOS        → family.calendar auto-populated
HealthOS        lab.results.available        FamilyOS        "Your results are ready — view interpretation"
HealthOS        immunization.due             FamilyOS        → family.reminders + PharmaOS scheduling
HealthOS        referral.created             FamilyOS        "Sleep specialist referral — find appointments?"

FinanceOS       plan.approved               FamilyOS        "Advisor approved college savings plan"
FinanceOS       budget.alert                FamilyOS        "Over budget on dining this month — adjust?"
FinanceOS       tax.estimated               FamilyOS        "Estimated refund: $3,200 — want to allocate?"
FinanceOS       milestone.reached           FamilyOS        "Emergency fund fully funded!"

BankOS          fraud.alert                 FinanceOS       Advisor sees unauthorized charge on client account
BankOS          loan.approved               FamilyOS        "Mortgage approved, closing date set for June 28"
BankOS          large.deposit               FinanceOS       Advisor sees income event — tax planning triggered

EnterpriseOS    leave.approved              FamilyOS        → family.calendar blocks parental leave period
EnterpriseOS    benefits.changed             FamilyOS        "New insurance cards available — update providers?"
EnterpriseOS    payroll.processed            FinanceOS       Advisor sees income update for client
EnterpriseOS    termination.notice           FamilyOS        "COBRA deadline in 60 days — budget impact: $-2,400/mo"
EnterpriseOS    promotion.granted            FamilyOS        "Congrats! Income changing — update budget?"

GovOS           benefits.approved            FamilyOS        "SNAP approved, $420/month — added to shopping payment"
GovOS           tax.refund.issued            FamilyOS        → FinanceOS: advisor sees refund
GovOS           permit.approved              EnterpriseOS    Business license active — open for operations
GovOS           court.date.scheduled         FamilyOS        → family.calendar + family.reminders

AgriOS          harvest.completed            FinanceOS       Farmer's advisor sees revenue event
AgriOS          commodity.price.alert        AgriOS          Another farm sees market shift — sell/hold decision
AgriOS          supply.chain.disruption      FamilyOS        "Dairy prices may rise 15% next week — stock up?"

PharmaOS        order.ready.for.pickup       FamilyOS        "Walgreens Preston Rd — Lisinopril ready, $12.40"
PharmaOS        order.fulfilled              HealthOS        Doctor knows patient picked up medication
PharmaOS        stock.low                    HealthOS        Doctor: "consider alternative — shortage expected"
PharmaOS        prior_auth.required          HealthOS        Doctor: "PA needed for prescribed medication"

─── FEEDBACK LOOP (FamilyOS → Professional OS) ───

FamilyOS        reminder.created             PharmaOS        "Patient arriving ~1:00 PM — prep bag, reduce wait"
FamilyOS        order.confirmed              HealthOS        Doctor knows prescription was filled
FamilyOS        vitals.updated               HealthOS        Doctor sees live BP, heart rate, sleep, adherence
FamilyOS        appointment.booked           HealthOS        Doctor's calendar updated, patient confirmed
FamilyOS        adherence.report             HealthOS        "Lisinopril: MISSED 4 of 7 days" ← behavioral reality
FamilyOS        symptoms.logged              HealthOS        Patient-reported symptoms in real time
FamilyOS        life_event.detected          FinanceOS       "New baby — advisor: update plan, 529, will, insurance"
```

---

### The Live Push Model vs. The Stale Pull Model

Epic, Cerner, Allscripts — they all have patient portals. But the patient
portal is a **pull model**:

```
Pull Model (every EHR today):
  Doctor remembers to check portal →
  Patient remembers to log in and update →
  Data is stale by definition →
  Doctor asks "are you taking your medication?" →
  Patient lies (unintentionally or not)
```

```
Push Model (FamilyOS + HealthOS):
  Patient's watch records BP →
  FamilyOS emits vitals.updated event →
  HealthOS receives it automatically →
  Doctor opens patient profile:
    "Blood pressure: 138/88 — this morning 7:43am"
    "Medication adherence: Lisinopril MISSED 4 of 7 days"
    "Sleep: avg 5.2hrs last week (down from 7.1)"
    → Doctor doesn't ask "are you taking your meds?"
    → Doctor sees the answer. It's already there.
```

---

### The Behavioral Reality Gap — Closed Architecturally

This is what no EHR system has ever achieved. The gap between what the chart
says and what the patient is actually doing at home is where most chronic
disease management fails.

With consent and event provenance, the doctor's workspace becomes a **live
patient snapshot**:

```
Doctor opens patient profile in HealthOS
    │
    │ "give me user snapshot"
    ▼
HealthOS pulls cross-OS event stream WITH CONSENT:

┌─────────────────────────────────────────────────────────┐
│  PATIENT SNAPSHOT — Emma Smith                          │
│                                                         │
│  FROM HealthOS (clinical):                              │
│  • Last visit: 2026-05-12, Dr. Johnson                  │
│  • Current Rx: Lisinopril 10mg, Metformin 500mg         │
│  • Last labs: HbA1c 7.2 (2026-04-01)                   │
│                                                         │
│  FROM FamilyOS (live, consent-gated):                   │
│  • Blood pressure: 138/88 — this morning 7:43am         │
│  • Heart rate trend: elevated last 3 days               │
│  • Sleep: avg 5.2hrs last week (down from 7.1)          │
│  • Medication adherence: Lisinopril MISSED 4 of 7 days  │
│  • Steps: 1,200/day (was 6,400 before last month)       │
│  • Weight: +4.2 lbs since last visit                    │
│                                                         │
│  FROM PharmaOS:                                         │
│  • Metformin refill: picked up 2026-06-01 ✓             │
│  • Lisinopril refill: NOT picked up — expired           │  ← !!!
│                                                         │
│  SYSTEM INFERENCE (cross-domain):                       │
│  • BP elevated — likely because Lisinopril not being    │
│    taken (adherence data confirms)                      │
│  • Sleep disruption correlating with BP spike           │
│  • Activity drop suggests fatigue or mood change        │
│  • Recommend: depression screening + sleep referral     │
└─────────────────────────────────────────────────────────┘
```

The doctor didn't have to ask four systems. Didn't have to call the pharmacy.
Didn't have to ask the patient "are you taking your medication?" — which
patients misreport anyway.

**The answer is already there. Real. Live. From the patient's actual life.**

And then the doctor acts:

*"Increase Lisinopril to 20mg, add a sleep referral, flag for depression screening"*

```
HealthOS:
    → new Rx issued → PharmaOS (Walgreens Preston Rd)
    → referral created → FamilyOS notification
    → depression screening flag → next appointment auto-scheduled

FamilyOS (Emma):
    "Dr. Johnson updated your prescription.
     Lisinopril is now 20mg — Walgreens Preston Rd
     has it ready tomorrow.
     Also: you have a sleep specialist referral.
     Want me to find available appointments this week?"

FamilyOS smart watch:
    → new BP monitoring schedule pushed
    → daily reading reminder set
    → data starts flowing back to HealthOS automatically

PharmaOS:
    → new prescription received
    → auto-fill triggered
    → ready notification emitted → FamilyOS
    → pickup scheduled (patient arriving ~1:00 PM per FamilyOS)
```

**The loop closes in both directions.** Doctor acts → patient's life updates →
data flows back → doctor sees the result. Zero manual data entry. Zero
"did you take your medication?" conversations. Just events at sovereign borders.

---

### The Compounding Moat

> Each OS becomes more valuable the more other OSes exist.

This isn't just network effects. It's **inter-OS composability**:

```
A financial planner using FinanceOS alone:
  → Portfolio tools, manual client data entry

A financial planner using FinanceOS connected to:
  → Client FamilyOS: sees actual spending patterns, not self-reported
  → BankOS: sees real-time fraud alerts, large deposits
  → EnterpriseOS: sees payroll, benefits changes, termination notices
  → GovOS: sees tax refunds, benefit approvals
  → HealthOS (with consent): sees long-term care planning needs

That financial planner now has a GOD-VIEW of the client's financial life
that no standalone tool can provide.

And the client never had to fill out a form.
The data arrived via events from sovereign OSes the client is already connected to.
```

Every new OS makes every existing OS more powerful:

- A doctor using HealthOS alone gets clinical tools
- A doctor using HealthOS connected to patient FamilyOS instances gets
  confirmation that prescriptions were filled, reminders were set, pickups
  happened, vitals are tracking, adherence is visible
- **The loop closes. The moat deepens with every domain.**

---

## The Two-Layer App Architecture — Every OS Follows the Same Pattern

Every OS in the 8-domain family uses the **same two-layer architecture**:

- **Layer 1 — Home:** The unified operational surface. Answers "what's happening?"
  and "what do I need to do?" across all domains. Pulls from all hubs.
  Chronological. Priority-ordered.

- **Layer 2 — Domain Hubs:** Depth surfaces for each life or operational domain.
  Show detail, history, trends, and domain-specific management tools. They are
  VIEWS on the shared data model — not separate apps with separate databases.

```
┌─────────────────────────────────────────────────────────┐
│              THE TWO-LAYER PATTERN                       │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              LAYER 1: HOME                        │  │
│  │                                                   │  │
│  │  Unified timeline. Everything. All hubs.           │  │
│  │  Calendar + Tasks + Reminders aggregated.          │  │
│  │  "What's next? What needs attention?"             │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                              │
│          ┌───────────────┼───────────────┐              │
│          │               │               │              │
│          ▼               ▼               ▼              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│  │ LAYER 2:     │ │ LAYER 2:     │ │ LAYER 2:     │    │
│  │ Domain Hub A │ │ Domain Hub B │ │ Domain Hub C │ .. │
│  │              │ │              │ │              │    │
│  │ Detail views │ │ Detail views │ │ Detail views │    │
│  │ History      │ │ History      │ │ History      │    │
│  │ Trends       │ │ Trends       │ │ Trends       │    │
│  │ Analytics    │ │ Analytics    │ │ Analytics    │    │
│  └──────────────┘ └──────────────┘ └──────────────┘    │
│                                                         │
│  ALL HUBS SHARE ONE DATA MODEL:                         │
│  appointments[]  tasks[]  reminders[]  items[]          │
│                                                         │
│  Hubs are FILTERED LENSES, not separate databases.      │
│  Create in any hub → appears in Home → synced to all.   │
└─────────────────────────────────────────────────────────┘
```

### The Shared Data Model

Layer 1 and Layer 2 are NOT separate apps with separate data. They are
two views of the **same underlying data model**:

```
                    ┌─────────────────┐
                    │   SHARED DATA   │
                    │     MODEL       │
                    │                 │
                    │  appointments[] │
                    │  tasks[]        │
                    │  reminders[]    │
                    │  items[]        │
                    │  domain_records[]│
                    │  ...            │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │  HOME VIEW   │ │ HUB A VIEW   │ │ HUB B VIEW   │
    │              │ │              │ │              │
    │ All appts    │ │ Domain A     │ │ Domain B     │
    │ All tasks    │ │ appts only   │ │ appts only   │
    │ All reminders│ │ Domain A     │ │ Domain B     │
    │ All items    │ │ tasks only   │ │ tasks only   │
    └──────────────┘ └──────────────┘ └──────────────┘
```

**The Four Rules:**

1. Anything with a time/date appears in Home Calendar — regardless of which hub created it.
2. Anything with a deadline or completion state appears in Home Tasks — regardless of domain.
3. Anything with a time-based trigger appears in Home Reminders — regardless of domain.
4. Domain hubs filter to their domain. Creating an item inside a hub also adds it to the shared store — so Home sees it. Cross-OS propagation happens automatically.

---

### FamilyOS — Two-Layer App Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FAMILYOS                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   LAYER 1: HOME                       │  │
│  │                                                       │  │
│  │  "What's happening? What do I need to do?"            │  │
│  │                                                       │  │
│  │  Unified calendar, tasks, reminders — all domains.     │  │
│  │  Chronological + priority-ordered feed.               │  │
│  │  Cross-OS events land here first.                     │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ ❤️ HEALTH    │ │ 💰 MONEY     │ │ 💼 WORK      │       │
│  │              │ │              │ │              │       │
│  │ Vitals       │ │ Spending     │ │ Leave        │       │
│  │ Medications  │ │ Budget       │ │ Benefits     │       │
│  │ Appointments │ │ Savings      │ │ Pay schedule │       │
│  │ Adherence    │ │ Bills        │ │ Work calendar│       │
│  │ Pharmacy     │ │ Taxes        │ │ Documents    │       │
│  │ Lab results  │ │ Insurance    │ │              │       │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘       │
│         │                │                │               │
│  ┌──────┴───────┐ ┌──────┴───────┐ ┌──────┴───────┐       │
│  │ 👨‍👩‍👧 FAMILY  │ │ 🛒 FOOD     │ │ 📋 PLANS    │       │
│  │              │ │              │ │              │       │
│  │ Kids calendar│ │ Grocery lists│ │ Events       │       │
│  │ School       │ │ Meal planning│ │ Travel       │       │
│  │ Caregiving   │ │ Prescriptions│ │ Big purchases│       │
│  │ Shared events│ │ Price compare│ │ Home projects│       │
│  │ Contacts     │ │ Order history│ │ Goals        │       │
│  └──────────────┘ └──────────────┘ └──────┬───────┘       │
│                                           │               │
│                                 ┌─────────┴─────────┐     │
│                                 │ ⚙️ SETTINGS       │     │
│                                 │                   │     │
│                                 │ Family members    │     │
│                                 │ Connected OSes    │     │
│                                 │ Permissions       │     │
│                                 │ Notification prefs│     │
│                                 └───────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

**Layer 1 — FamilyOS Home:**

```
┌──────────────────────────────────────────────┐
│  🏠 Good morning, Emma                   ☀️  │
│                                              │
│  ⚠️ Lisinopril — you missed yesterday         │
│     [I took it now] [Remind me tonight]      │
│                                              │
│  📅 TODAY                                    │
│  ├── 2:00p  Dr. Chen — cardiology           │
│  ├── 4:30p  Riley soccer practice           │
│  └── 7:00p  Family dinner (Mom cooking)     │
│                                              │
│  ✅ NEEDS ATTENTION                          │
│  ├── 🏦 Sign mortgage docs — due Friday     │
│  ├── 💊 Refill Emma's inhaler — 12 days     │
│  └── 🛒 Meal plan for next week             │
│                                              │
│  📥 INBOX (cross-OS events)                  │
│  ├── 🏥 Dr. Chen: new prescription           │
│  ├── 💊 Walgreens: medication ready          │
│  └── 💼 Work: leave approved Jun 30          │
│                                              │
│  [Type anything...]                          │
└──────────────────────────────────────────────┘
```

**Layer 2 — Health Hub (example):**

```
┌──────────────────────────────────────────────┐
│  ← Home    ❤️ Health                         │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │ VITALS (from FamilyOS wearables)      │    │
│  │ BP: 138/88 today · HR: 72 bpm        │    │
│  │ Sleep: 5.2hrs avg · Steps: 1,200     │    │
│  │ [View 3-month trends →]              │    │
│  └──────────────────────────────────────┘    │
│                                              │
│  📅 APPOINTMENTS  ← SAME calendar as Home    │
│  ├── Jun 18  2:00p  Dr. Chen (cardiology)   │
│  ├── Jun 20  8:00a  Dentist (Emma)          │
│  └── Jul 05  9:30a  Sleep specialist        │
│  [+ New appointment]                         │
│      ↑ adds to Home calendar AND Health hub  │
│      ↑ emits event to HealthOS if connected  │
│                                              │
│  💊 MEDICATIONS                              │
│  ├── Lisinopril 20mg · daily                │
│  │   ⚠️ Took 3 of 7 days this week         │
│  ├── Metformin 500mg · 2x daily · ✓ On track│
│  └── Emma: Albuterol · Refill in 12 days    │
│                                              │
│  📋 LAB RESULTS (from HealthOS)              │
│  ├── HbA1c: 7.2 — Apr 1, 2026              │
│  └── Lipid panel: pending                   │
│                                              │
│  📜 PRESCRIPTIONS (from HealthOS)            │
│  └── Lisinopril 20mg — Dr. Sarah Chen       │
│      Issued Jun 13 · Filled at Walgreens     │
└──────────────────────────────────────────────┘
```

**The Bidirectional Sync:** Add a dentist appointment in Health Hub →
appears in Home Calendar → emits event to HealthOS if connected.
Doctor schedules appointment in HealthOS → event lands in FamilyOS →
appears in Home Calendar AND Health Hub. Same data. Different lenses.

---

### HealthOS — Two-Layer Clinical Architecture

HealthOS isn't for patients. It's for doctors, nurses, and hospitals.
Its "Home" is the clinical workspace. Its hubs are clinical domains.

```
┌─────────────────────────────────────────────────────────────┐
│                     HEALTHOS                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              LAYER 1: CLINIC VIEW                     │  │
│  │                                                       │  │
│  │  "Who am I seeing today? What needs my attention?"    │  │
│  │                                                       │  │
│  │  Today's patient schedule. Pending labs.              │  │
│  │  Unreviewed results. Prescription renewals.           │  │
│  │  Cross-OS patient snapshots (from FamilyOS).          │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 📋 RECORDS   │ │ 📅 APPOINT.  │ │ 💊 MEDS      │       │
│  │              │ │              │ │              │       │
│  │ Patient chart│ │ Schedule     │ │ Prescribe    │       │
│  │ History      │ │ Availabilty  │ │ Interactions │       │
│  │ Lab results  │ │ Telehealth   │ │ Formulary    │       │
│  │ Imaging      │ │ Follow-ups   │ │ Refills      │       │
│  │ Immunizations│ │ Waitlist     │ │ Prior auth   │       │
│  └──────────────┘ └──────────────┘ └──────┬───────┘       │
│                                           │               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────┴───────┐       │
│  │ 🫀 VITALS    │ │ 🛡️ INSURANCE│ │ 👨‍👩‍👧 FAMILY   │       │
│  │              │ │              │ │   VIEW       │       │
│  │ Patient      │ │ Coverage     │ │              │       │
│  │  vitals      │ │  check       │ │ Patient's    │       │
│  │ Wearable data│ │ Prior auth   │ │  live data   │       │
│  │ Trends       │ │ Claims       │ │  from FamilyOS│      │
│  │ Alerts       │ │ Referrals    │ │ Adherence    │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ⚙️ PRACTICE SETTINGS                                      │
│  Providers · Locations · Scheduling rules · Templates       │
└─────────────────────────────────────────────────────────────┘
```

**Key difference from FamilyOS:** HealthOS hubs are **clinical tools** —
they don't just display data, they are the doctor's instruments.
`health.records` is where the doctor writes notes. `health.medications`
is where the doctor prescribes. `health.appointments` is where the front
desk schedules. The hubs ARE the EHR.

---

### BankOS — Two-Layer Banking Architecture

BankOS is for bank employees. Its "Home" is the **bank view** — the
operational command center for a financial institution.

```
┌─────────────────────────────────────────────────────────────┐
│                       BANKOS                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              LAYER 1: BANK VIEW                       │  │
│  │                                                       │  │
│  │  "What's happening across the institution?"           │  │
│  │                                                       │  │
│  │  Real-time transaction volume. Fraud alerts.          │  │
│  │  Pending approvals. Regulatory deadlines.             │  │
│  │  Cross-OS events (FinanceOS, GovOS, EnterpriseOS).    │  │
│  │  Liquidity position. Settlement status.               │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 👤 CUSTOMERS │ │ 💳 TRANSACT. │ │ ⚖️ COMPLIANCE│       │
│  │              │ │              │ │              │       │
│  │ Customer 360 │ │ Payment route│ │ AML screening│       │
│  │ KYC verify   │ │ FX rates     │ │ Sanctions    │       │
│  │ Risk score   │ │ Settlement   │ │ Reg. filings │       │
│  │ Onboarding   │ │ Reconcile    │ │ Audit trail  │       │
│  │ Comms history│ │ Analytics    │ │ Attestations │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 🏠 LENDING   │ │ 🚨 FRAUD     │ │ 🏦 TREASURY  │       │
│  │              │ │              │ │              │       │
│  │ Credit check │ │ Fraud score  │ │ Cash position│       │
│  │ Underwriting │ │ Device intel │ │ Liquidity    │       │
│  │ Portfolio    │ │ Behavioral   │ │ FX exposure  │       │
│  │ Collections  │ │ Case mgmt    │ │ Funding      │       │
│  │ Loss mitig.  │ │ Network      │ │ Collateral   │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ⚙️ INSTITUTION SETTINGS                                   │
│  Branches · Products · Rate cards · Regulatory profiles     │
└─────────────────────────────────────────────────────────────┘
```

**Bank View (Home) — what a bank employee sees:**

```
┌──────────────────────────────────────────────┐
│  🏦 Good morning, Sarah                  📊  │
│                                              │
│  ⚠️ 3 fraud alerts requiring review           │
│     [Review now]                             │
│                                              │
│  📊 TODAY'S NUMBERS                          │
│  ├── Transactions: 47,231 · +3% vs yesterday │
│  ├── Settlement: $2.1B · 98.7% cleared       │
│  └── Liquidity: $847M · 104% of requirement  │
│                                              │
│  📋 PENDING APPROVALS                        │
│  ├── Loan #L-8842 — $1.2M commercial RE      │
│  ├── KYC exceptions — 12 accounts            │
│  └── Wire transfer > $5M — 3 pending         │
│                                              │
│  📥 CROSS-OS EVENTS                          │
│  ├── 🏛 GovOS: 3 new business licenses       │
│  ├── 💼 EnterpriseOS: payroll batch received  │
│  └── 💰 FinanceOS: large deposit flagged     │
│                                              │
│  [Type anything...]                          │
└──────────────────────────────────────────────┘
```

---

### FinanceOS — Two-Layer Advisory Architecture

FinanceOS is for financial planners, CPAs, and wealth advisors.
Its "Home" is the **advisor dashboard**.

```
┌─────────────────────────────────────────────────────────────┐
│                     FINANCEOS                               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           LAYER 1: ADVISOR VIEW                       │  │
│  │                                                       │  │
│  │  "Which clients need attention today?"                │  │
│  │                                                       │  │
│  │  Client portfolio summaries. Life events.             │  │
│  │  Market alerts. Tax deadlines. Plan reviews due.      │  │
│  │  Cross-OS events (BankOS fraud, EnterpriseOS payroll, │  │
│  │  HealthOS diagnosis with consent).                    │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 🏦 ACCOUNTS  │ │ 📈 INVESTMENTS│ │ 💵 BUDGET    │       │
│  │              │ │              │ │              │       │
│  │ All balances │ │ Portfolio    │ │ Budget vs    │       │
│  │ Transactions │ │ Performance  │ │  actual      │       │
│  │ Transfers    │ │ Allocation   │ │ Cash flow    │       │
│  │ Categories   │ │ Tax loss     │ │  forecast    │       │
│  │ Net worth    │ │ Crypto       │ │ Savings goals│       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 📄 TAXES     │ │ 🏠 LOANS     │ │ 🛡️ INSURANCE│       │
│  │              │ │              │ │              │       │
│  │ Gather docs  │ │ All loans    │ │ All policies │       │
│  │ Estimate tax │ │ Refinance    │ │ Compare      │       │
│  │ Deductions   │ │ Payoff       │ │  quotes      │       │
│  │ File return  │ │  forecast    │ │ File claim   │       │
│  │ Track refund │ │ Forbearance  │ │ Renewals     │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ⚙️ PRACTICE SETTINGS                                      │
│  Client roster · Compliance · Fee schedules · Templates     │
└─────────────────────────────────────────────────────────────┘
```

---

### EnterpriseOS — Two-Layer Business Architecture

EnterpriseOS is for companies. Its "Home" is the **workspace** — the
employee and manager command center. Each hub is a department.

```
┌─────────────────────────────────────────────────────────────┐
│                   ENTERPRISEOS                              │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │             LAYER 1: WORKSPACE                        │  │
│  │                                                       │  │
│  │  "What's happening at work today?"                    │  │
│  │                                                       │  │
│  │  My meetings. My tasks. Team status.                  │  │
│  │  Pending approvals. Company announcements.            │  │
│  │  Cross-OS events (employee life events → FamilyOS).   │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 💬 COMMS     │ │ 👥 HR        │ │ 💰 FINANCE   │       │
│  │              │ │              │ │              │       │
│  │ All messages │ │ My profile   │ │ Expenses     │       │
│  │ Meetings     │ │ Payroll      │ │ Invoicing    │       │
│  │ Inbox        │ │ Benefits     │ │ Budget       │       │
│  │ Presence     │ │ PTO calendar │ │ Revenue      │       │
│  │ Search       │ │ Performance  │ │ Close        │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 🤝 CRM       │ │ ⚙️ DEVOPS    │ │ ⚖️ LEGAL     │       │
│  │              │ │              │ │              │       │
│  │ Customer 360 │ │ Incidents    │ │ Contracts    │       │
│  │ Pipeline     │ │ Deployments  │ │ Review       │       │
│  │ Health score │ │ Infra view   │ │ Compliance   │       │
│  │ Renewals     │ │ Cost opt.    │ │ Litigation   │       │
│  │ Churn risk   │ │ On-call      │ │ IP portfolio │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐                         │
│  │ 📣 MARKETING │ │ 🖥️ IT        │                         │
│  │              │ │              │                         │
│  │ Campaigns    │ │ Tickets      │                         │
│  │ Journeys     │ │ Assets       │                         │
│  │ Content      │ │ Access       │                         │
│  │ Attribution  │ │ Security     │                         │
│  │ Competitors  │ │ Changes      │                         │
│  └──────────────┘ └──────────────┘                         │
│                                                             │
│  ⚙️ COMPANY SETTINGS                                       │
│  Departments · Roles · Policies · Integrations              │
└─────────────────────────────────────────────────────────────┘
```

**EnterpriseOS Home is role-dependent:** An employee sees their own tasks,
calendar, and approvals. A manager sees team status and pending reviews.
An executive sees cross-department dashboards. Same Home surface.
Different lenses based on role.

---

### GovOS — Two-Layer Government Architecture

GovOS faces two user classes: **citizens** and **agency staff**.
Each gets a different Home view.

```
┌─────────────────────────────────────────────────────────────┐
│                       GOVOS                                 │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           LAYER 1: AGENCY VIEW (staff) /              │  │
│  │                    CITIZEN VIEW (public)              │  │
│  │                                                       │  │
│  │  STAFF: "What cases need processing today?"           │  │
│  │  CITIZEN: "What's the status of my applications?"     │  │
│  │                                                       │  │
│  │  Case queues. Pending reviews. Deadlines.             │  │
│  │  Cross-OS events (court dates, benefits, permits).    │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 🏛 CITIZEN   │ │ 📋 PERMITTING│ │ 💵 BENEFITS  │       │
│  │   SERVICES   │ │              │ │              │       │
│  │              │ │              │ │              │       │
│  │ My cases     │ │ Requirements │ │ Eligibility  │       │
│  │ Apply        │ │ Submit permit│ │ Calculate    │       │
│  │ Appointments │ │ Inspections  │ │ Recertify    │       │
│  │ Vital records│ │ Licenses     │ │ Fraud detect │       │
│  │ Notifications│ │ Env. review  │ │ Payments     │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 📄 TAX       │ │ 🚨 SAFETY    │ │ 🏗 INFRA     │       │
│  │              │ │              │ │              │       │
│  │ File return  │ │ Alerts       │ │ Roads        │       │
│  │ Check refund │ │ Reports      │ │ Transit      │       │
│  │ Payment plan │ │ Evacuation   │ │ Utilities    │       │
│  │ Audit support│ │ Shelters     │ │ Waste        │       │
│  │ Estimate     │ │ Disaster aid │ │ Projects     │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ⚙️ AGENCY SETTINGS                                        │
│  Jurisdictions · Forms · Workflows · Public portals         │
└─────────────────────────────────────────────────────────────┘
```

---

### AgriOS — Two-Layer Agricultural Architecture

AgriOS is for farmers, ranchers, and agribusiness. Its "Home" is the
**farm view** — everything happening across the operation.

```
┌─────────────────────────────────────────────────────────────┐
│                       AGRIOS                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              LAYER 1: FARM VIEW                       │  │
│  │                                                       │  │
│  │  "What's happening on the farm today?"                │  │
│  │                                                       │  │
│  │  Field conditions. Weather alerts. Equipment status.  │  │
│  │  Market prices. Harvest schedule. Livestock health.   │  │
│  │  Cross-OS events (commodity prices, supply chain).    │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 🌾 CROPS     │ │ 🐄 LIVESTOCK │ │ 📊 MARKET    │       │
│  │              │ │              │ │              │       │
│  │ Field health │ │ Herd health  │ │ Commodity    │       │
│  │ Soil analysis│ │ Breeding     │ │  prices      │       │
│  │ Planting     │ │ Milk prod.   │ │ Contracts    │       │
│  │ Yield pred.  │ │ Weight track │ │ Forecasts    │       │
│  │ Pest alerts  │ │ Movement     │ │ Find buyer   │       │
│  │ Irrigation   │ │              │ │ Sell crop    │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 🚜 EQUIPMENT │ │ 🌦 WEATHER   │ │ 📦 SUPPLY    │       │
│  │              │ │              │ │   CHAIN      │       │
│  │ Fleet status │ │ Field        │ │              │       │
│  │ Maintenance  │ │  forecast    │ │ Inventory    │       │
│  │ Fuel usage   │ │ GDD tracking │ │ Logistics    │       │
│  │ Utilization  │ │ Frost risk   │ │ Quality      │       │
│  │ Service req. │ │ Precip. data │ │ Traceability │       │
│  │ Downtime cost│ │ Drought      │ │ Certs        │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ⚙️ FARM SETTINGS                                          │
│  Fields · Equipment fleet · Livestock herds · Certifications│
└─────────────────────────────────────────────────────────────┘
```

---

### PharmaOS — Two-Layer Pharmacy Architecture

PharmaOS is for pharmacists and pharmacy chains. Its "Home" is the
**pharmacy dashboard** — the fulfillment queue.

```
┌─────────────────────────────────────────────────────────────┐
│                     PHARMAOS                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            LAYER 1: PHARMA VIEW                       │  │
│  │                                                       │  │
│  │  "What needs to be filled right now?"                 │  │
│  │                                                       │  │
│  │  Prescription queue. Wait times. Inventory alerts.    │  │
│  │  Prior auth pending. Pickup schedule.                 │  │
│  │  Cross-OS events (new Rx from HealthOS,               │  │
│  │  patient ETA from FamilyOS, doctor queries).          │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│          ┌───────────────┼───────────────┐                 │
│          │               │               │                 │
│          ▼               ▼               ▼                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 💊 FULFILL   │ │ 📦 INVENTORY │ │ 🛡️ INSURANCE│       │
│  │              │ │              │ │              │       │
│  │ Receive Rx   │ │ Stock levels │ │ Adjudicate   │       │
│  │ Verify       │ │ Auto-reorder │ │ Prior auth   │       │
│  │ Fill         │ │ Cold chain   │ │ Copay calc   │       │
│  │ RPh review   │ │ Drug recall  │ │ Coupons      │       │
│  │ Pickup       │ │ Controlled   │ │ Medicare D   │       │
│  │ Delivery     │ │ Returns      │ │              │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 👤 CUSTOMER  │ │ ⚖️ COMPLIANCE│ │ 🧪 COMPOUND  │       │
│  │              │ │              │ │              │       │
│  │ Notifications│ │ DEA tracking │ │ Formulas     │       │
│  │ Reminders    │ │ HIPAA audit  │ │ Batch track  │       │
│  │ Counseling   │ │ Board regs   │ │ Quality test │       │
│  │ Surveys      │ │ USP 797/800  │ │ Custom pack  │       │
│  │              │ │ Error report │ │              │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ⚙️ PHARMACY SETTINGS                                      │
│  Locations · Hours · Staff · Wholesaler accounts · PBMs     │
└─────────────────────────────────────────────────────────────┘
```

**Pharma View (Home) — what a pharmacist sees:**

```
┌──────────────────────────────────────────────┐
│  💊 Good morning, Dr. Kim (PharmD)      📋   │
│                                              │
│  ⚠️ 3 prescriptions expiring in < 1 hour      │
│     [Prioritize these]                       │
│                                              │
│  📋 FILL QUEUE                               │
│  ├── 🔴 Lisinopril 20mg — Emma Smith         │
│  │    Patient arriving ~1:00 PM              │
│  ├── 🟡 Metformin 500mg — John Davis         │
│  │    Prior auth pending — waiting           │
│  └── 🟢 Amoxicillin — New Rx from Dr. Chen   │
│                                              │
│  📅 PICKUP SCHEDULE                          │
│  ├── 11:30a  Mrs. Garcia — Atorvastatin      │
│  ├── 1:00p   Emma Smith — Lisinopril         │
│  └── 3:00p   Mr. Thompson — Insulin          │
│                                              │
│  📥 CROSS-OS EVENTS                          │
│  ├── 🏥 HealthOS: 2 new e-prescriptions      │
│  ├── 🏠 FamilyOS: Emma arriving ~1:00 PM     │
│  └── 📦 Wholesaler: Restock arrived          │
│                                              │
│  [Type anything...]                          │
└──────────────────────────────────────────────┘
```

---

### The Pattern Summary

Every OS domain follows the exact same structural pattern:

| OS | Layer 1 Name | What It Answers | Layer 2 Hubs (Count) |
|----|-------------|-----------------|---------------------|
| **FamilyOS** | Home | "What's happening in my family's life?" | Health, Money, Work, Family, Food, Plans, Settings (7) |
| **HealthOS** | Clinic View | "Who am I seeing today? What needs clinical attention?" | Records, Appointments, Meds, Vitals, Insurance, Family View, Settings (7) |
| **FinanceOS** | Advisor View | "Which clients need attention today?" | Accounts, Investments, Budget, Taxes, Loans, Insurance, Settings (7) |
| **BankOS** | Bank View | "What's happening across the institution?" | Customers, Transactions, Compliance, Lending, Fraud, Treasury, Settings (7) |
| **EnterpriseOS** | Workspace | "What's happening at work today?" | Comms, HR, Finance, CRM, DevOps, Legal, Marketing, IT, Settings (9) |
| **GovOS** | Agency View / Citizen View | "What cases need processing?" / "What's my status?" | Citizen Services, Permitting, Benefits, Tax, Safety, Infrastructure, Settings (7) |
| **AgriOS** | Farm View | "What's happening on the farm today?" | Crops, Livestock, Market, Equipment, Weather, Supply Chain, Settings (7) |
| **PharmaOS** | Pharma View | "What needs to be filled right now?" | Fulfillment, Inventory, Insurance, Customer, Compliance, Compounding, Settings (7) |

All share:

- **One shared data model** underneath — hubs are filtered lenses, not separate databases
- **Bidirectional sync** between Layer 1 and Layer 2 — create anywhere, appears everywhere
- **Cross-OS propagation** — relevant events emitted to and received from other OSes
- **Role-dependent views** — the same Hub looks different based on who's looking

---

## Cross-Cutting Architecture Patterns

### Pattern 1: Fan-Out with Partial Failure Tolerance

Every native app implements the same fan-out pattern:

```python
async def fan_out_to_backends(
    user_id: str,
    native_app: str,
    operation: str,
    payload: dict,
) -> AggregatedResult:
    """Pattern used by EVERY native app for EVERY multi-backend operation."""

    # 1. Discover which backends this user has connected
    backends = await registry.get_user_backends(user_id, native_app)

    # 2. Fan out in parallel — never sequential
    tasks = [
        backend.execute(operation, payload)
        for backend in backends
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 3. Classify results
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [
        (backend, r) for backend, r in zip(backends, results)
        if isinstance(r, Exception)
    ]

    # 4. Aggregate successes, annotate failures
    return AggregatedResult(
        results=successes,
        partial_failures=failures,
        total_backends=len(backends),
        successful_backends=len(successes),
        is_degraded=len(failures) > 0,
        # NEVER fail the whole call because one backend is down
    )
```

### Pattern 2: Read/Write Security Gating

| Operation Type | Back LLM Can... | User Confirmation Required |
|----------------|-----------------|---------------------------|
| **Read** (list, get, search, compare) | Call directly | No |
| **Non-financial Write** (create event, add item) | Call directly | No (undoable) |
| **Financial Write** (place order, transfer funds) | Call with confirmation | **YES** — HITL gate |
| **Irreversible Write** (delete account, close loan) | Call with confirmation | **YES** — double-confirm |
| **Security Change** (change password, unlink account) | **NEVER** | **YES** — re-authentication |

### Pattern 3: Schema Normalization Layer

Every native app has a normalization layer that converts backend-specific schemas to the native app's canonical schema:

```
Backend A (Walmart):        Backend B (Kroger):           Native App (Canonical):
{                           {                              {
  "itemId": "123",            "product_id": "456",          "item_id": "walmart:123",
  "price": 3.49,              "current_price": 3.29,        "name": "Organic Whole Milk",
  "currency": "USD",          "unit": "gallon",             "price": 3.49,
  "name": "Organic Milk"      "desc": "Organic Milk"        "unit": "gallon",
}                           }                              "unit_price": 3.49,
                              ↓                              "store": "Walmart",
                    [Normalize] → [Normalize]                "distance_mi": 1.2,
                              ↓                              "in_stock": true,
                         ┌────────┐                         "backend": "walmart-api"
                         │ CANON  │                       }
                         └────────┘
```

### Pattern 4: Backend Health Scoring

```python
@dataclass
class BackendHealth:
    backend_id: str
    latency_p50_ms: float
    latency_p99_ms: float
    error_rate_1h: float
    success_rate_24h: float
    last_success: datetime
    consecutive_failures: int

    @property
    def is_healthy(self) -> bool:
        return (
            self.error_rate_1h < 0.05
            and self.consecutive_failures < 3
            and self.latency_p99_ms < self.timeout_ms
        )

    @property
    def should_circuit_break(self) -> bool:
        return self.consecutive_failures >= 5
```

When a backend circuit-breaks, the native app continues with degraded results from remaining backends. The user sees "Kroger: temporarily unavailable" — never an error.

### Pattern 5: User-Controlled Backend Connections

```
┌──────────────────────────────────────────────────┐
│  family.shopping → Connected Accounts             │
│  ┌──────────────────────────────────────────┐    │
│  │ ☑ Walmart      (connected 2026-03-15)    │    │
│  │ ☑ Kroger       (connected 2026-01-10)    │    │
│  │ ☑ Costco       (connected 2026-05-20)    │    │
│  │ ☐ Instacart    (tap to connect)          │    │
│  │ ☐ Amazon Fresh (tap to connect)          │    │
│  │ ☐ Target       (tap to connect)          │    │
│  │                                          │    │
│  │ [+ Connect New Account]                  │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

The user — NOT the LLM — decides which backends to connect. The native app queries only connected backends. Adding a new backend is an OAuth flow, not an LLM routing decision.

---

## Implications for Connector Search

### What the Search NO LONGER Needs to Do

| Old Requirement | Why Gone |
|-----------------|----------|
| Distinguish `family.shopping` from `grocery_comp.instacart` | Instacart is a backend, not a visible connector |
| Distinguish `family.tasks` from `todo_comp.todoist` | Todoist is a backend to family.tasks |
| Distinguish `family.calendar` from `scheduling_comp.calendly` | Calendly is a backend |
| Competing distractor benchmark queries | No competing connectors exist |
| 70-way connector arbitration | Max 6-way per domain, with clear semantic boundaries |

### What the Search ONLY Needs to Do

1. **Domain-level routing**: "add milk to cart" → shopping → `family.shopping`. That's it.
2. **Cross-domain disambiguation**: "schedule a grocery run" → is this calendar or shopping? (This is already solved by the boundary fields.)
3. **Multi-OS routing**: If multiple OS domains are active (FamilyOS + HealthOS), which native app handles this query?

### Benchmark Simplification

The 70 competing distractors (`grocery_comp.*`, `todo_comp.*`, etc.) should be **removed** from the connector search benchmark. They model the wrong architecture.

Instead, the benchmark should test:

1. **Domain-level accuracy**: 6-way classification (shopping vs tasks vs calendar vs chores vs reminders vs settings)
2. **Cross-OS accuracy**: When HealthOS is also present, does "check my blood pressure" route to `health.vitals` and not `family.reminders`?
3. **Scale**: 193 semantically-diverse distractors (banking, IoT, health, etc.) + 6 native apps. No competing distractors.

---

## Migration Impact on Resolver Redesign

### Issues That Become Irrelevant (Can Be Closed)

| RES Issue | Reason Closed |
|-----------|---------------|
| RES-004 (multi-connector ambiguity) | No more competing shopping connectors |
| RES-005 (connector alternatives in envelope) | Envelope only needs one connector_id |
| RES-006 (HITL for connector selection) | No selection to make — one native app per domain |
| RES-009 (session context for disambiguation) | Brand-signal queries (Instacart by name) are backends, not connectors |

### Issues That Remain but Are Simplified

| RES Issue | Simplification |
|-----------|---------------|
| RES-001 (connector search) | 6-way classification instead of 76-way |
| RES-002 (build_connector_documents) | No competing distractor documents to build |
| RES-003 (search_connectors SQL) | Simpler query — no need for boundary-field disambiguation |
| RES-007 (CapabilityTypeResolver replacement) | Only resolves domain-level, not connector-level |
| RES-008 (ResolutionEnvelope) | No `alternatives` field needed for cross-connector |

### New Issues That Emerge

| New Issue | Description |
|-----------|-------------|
| RES-N01 | Backend connector registration — lightweight manifest format for data backends (not full admission) |
| RES-N02 | Fan-out execution pattern — asyncio.gather with partial failure tolerance as a kernel primitive |
| RES-N03 | Schema normalization layer — canonical schema per native app + per-backend mappers |
| RES-N04 | Backend health scoring & circuit breaking — embed in native app runtime |
| RES-N05 | User backend connection management — OAuth flow, token storage, connection CRUD |
| RES-N06 | Cross-OS routing — when FamilyOS and HealthOS are both active, route to correct OS |
| RES-N07 | Security gating — read/write/financial/irreversible operation tiers per native app |

---

## Summary: How This Design Scales

```
                         ┌─────────────────┐
                         │    ONE Back LLM  │
                         │ sees ~50 tools   │
                         │ (not 2000+)     │
                         └────────┬────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
    ┌─────┴─────┐          ┌─────┴─────┐          ┌─────┴─────┐
    │ FamilyOS   │          │ HealthOS   │          │ FinanceOS  │   ...
    │ 6 apps     │          │ 7 apps     │          │ 6 apps     │
    │ ~200 BEs   │          │ ~300 BEs   │          │ ~500 BEs   │
    └─────┬─────┘          └─────┬─────┘          └─────┬─────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                        ┌────────┴────────┐
                        │  IFL EVENT BUS  │
                        │                 │
                        │  Events only at │
                        │  OS borders.    │
                        │  Zero shared    │
                        │  databases.     │
                        └────────┬────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
    ┌─────┴─────┐          ┌─────┴─────┐          ┌─────┴─────┐
    │ PharmaOS   │          │  GovOS    │          │  AgriOS   │   ...
    │ 6 apps     │          │ 6 apps    │          │ 6 apps    │
    │ ~50 BEs    │          │ ~500 BEs  │          │ ~300 BEs  │
    └───────────┘          └───────────┘          └───────────┘

    8 OS domains × 6-8 native apps × 20-500+ data backends per app
    Total at scale: ~50 native apps, ~600-2500 data backends
```

The architecture scales across two dimensions:

**Dimension 1 — Within-OS (Aggregation):**

1. **The Back LLM sees a flat list of ~50 tools** — not 2000+
2. **Data backend registration is lightweight** — no admission manifest, no constitution, no policy. Just endpoint URL, auth, and schema mapping.
3. **Native apps handle all the complexity** — fan-out, normalization, partial failure, comparison, aggregation
4. **The user controls backend connections** — not the LLM, not the resolver

**Dimension 2 — Cross-OS (Event Mesh):**
5. **Each domain is sovereign** — they don't share data, they share events at borders
6. **Events flow bidirectionally** — professional OS → FamilyOS (downward), FamilyOS → professional OS (feedback loop)
7. **FamilyOS is the terminal consumer node** — every professional OS eventually touches a family
8. **The behavioral reality gap is closed** — professionals see live, real data from the patient's/client's actual life, not stale self-reports
9. **Inter-OS composability creates a compounding moat** — every new OS makes every existing OS more powerful

This is the platform architecture. The connector search POC benchmark was testing the WRONG problem — it was testing "which of 76 shopping connectors wins?" when the real question is "does this query route to shopping (family.shopping) or calendar (family.calendar)?" — a domain-level classification, not connector arbitration.

---

## What a Developer Actually Builds — The Full Stack

Developers building inside a cognitive OS domain ecosystem aren't writing one YAML file — they're building a **full native app stack** that ingests from 100+ backend connectors simultaneously. The connector definition YAML is 5% of the work. Here is the real scope.

```
┌─────────────────────────────────────────────────────────────────────┐
│              DEVELOPER BUILDS ALL OF THIS                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 1. NATIVE APP UI (React/Vite or Streamlit)                  │    │
│  │    ─────────────────────────────────────                    │    │
│  │    • Meal plan calendar view                                │    │
│  │    • Recipe browser with dietary filter chips               │    │
│  │    • Grocery list with drag-to-reorder                      │    │
│  │    • Price comparison table (color-coded by store)          │    │
│  │    • Order confirmation with split-backend tracking         │    │
│  │    • Family member dietary profiles                         │    │
│  │    • Nutritional dashboard (weekly macros, deficits)        │    │
│  │    • "Cook tonight" mode with step-by-step timer            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 2. CONNECTOR DEFINITION (what resolver indexes)             │    │
│  │    ─────────────────────────────────────                    │    │
│  │    connector_id, label, description, domain_id              │    │
│  │    12-18 tools with full JSON schemas                       │    │
│  │    constitution with teaching surface                       │    │
│  │    concept_aliases, operation_aliases                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 3. TOOL IMPLEMENTATIONS (Python — what invoke_capability    │    │
│  │    actually runs)                                           │    │
│  │    ─────────────────────────────────────                    │    │
│  │    plan_meals()       → check dietary profiles → generate   │    │
│  │    generate_list()    → meal plan → grocery items           │    │
│  │    place_order()      → fan out to 6+ food delivery APIs    │    │
│  │    price_compare()    → parallel query 15+ grocery APIs     │    │
│  │    track_nutrition()  → aggregate from wearables + manual   │    │
│  │    suggest_recipes()  → semantic search across 50+ sources  │    │
│  │    manage_dietary()   → per-member restriction CRUD         │    │
│  │    ...8+ more tools                                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 4. BACKEND CONNECTORS (100+ external API integrations)      │    │
│  │    ─────────────────────────────────────                    │    │
│  │    Grocery: Walmart, Kroger, Costco, ALDI, Target,          │    │
│  │             Whole Foods, Trader Joe's, Publix, Safeway,     │    │
│  │             Wegmans, HEB, Amazon Fresh, Instacart...        │    │
│  │    Delivery: DoorDash, Uber Eats, Grubhub, Postmates,       │    │
│  │              Slice, ChowNow, ezCater...                     │    │
│  │    Recipes: Spoonacular, Edamam, Tasty, AllRecipes,         │    │
│  │             FoodNetwork, NYT Cooking, Yummly...             │    │
│  │    Nutrition: USDA FoodData, Nutritionix, FatSecret,        │    │
│  │               MyFitnessPal, Cronometer...                    │    │
│  │    Meal Kits: HelloFresh, Blue Apron, Home Chef,            │    │
│  │               Green Chef, EveryPlate, Marley Spoon...       │    │
│  │    Each backend needs:                                      │    │
│  │      • API client (auth, rate limiting, retry, pagination)  │    │
│  │      • Schema normalization (backend format → canonical)    │    │
│  │      • Error mapping (backend errors → FamilyOS errors)     │    │
│  │      • Health check endpoint                                │    │
│  │      • Circuit breaker config                               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 5. SCHEMA NORMALIZATION (per-backend translation layer)     │    │
│  │    ─────────────────────────────────────                    │    │
│  │    Each backend speaks a different language:                │    │
│  │                                                             │    │
│  │    Walmart:   {itemId, productName, price, currency}        │    │
│  │    Kroger:    {product_id, desc, current_price, unit}       │    │
│  │    DoorDash:  {item.external_id, item.name,                 │    │
│  │                item.price_display_string}                   │    │
│  │    Spoonacular: {id, title, image, nutrition.nutrients[]}   │    │
│  │                                                             │    │
│  │    ALL NORMALIZED TO CANONICAL:                             │    │
│  │    {                                                        │    │
│  │      item_id: str,        name: str,                        │    │
│  │      price: float,        currency: str,                    │    │
│  │      unit: str,           unit_price: float,                │    │
│  │      store: str,          in_stock: bool,                   │    │
│  │      image_url: str,      nutrition: {...},                 │    │
│  │      dietary_tags: [...], allergens: [...]                  │    │
│  │    }                                                        │    │
│  │                                                             │    │
│  │    100+ normalizers to write. Each 50-200 lines.            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 6. FAN-OUT ORCHESTRATION (parallel backend execution)       │    │
│  │    ─────────────────────────────────────                    │    │
│  │    async def place_order(items, user_id):                   │    │
│  │        backends = await get_connected_backends(             │    │
│  │            user_id, app="family.food")                      │    │
│  │        # Fan out to 6 delivery backends in parallel         │    │
│  │        results = await asyncio.gather(*[                   │    │
│  │            backend.place_order(items)                       │    │
│  │            for backend in backends                          │    │
│  │        ], return_exceptions=True)                           │    │
│  │        # Partial failure? Return what succeeded.            │    │
│  │        # Circuit break? Skip that backend next time.        │    │
│  │        # Timeout? Mark degraded, return partial.            │    │
│  │        return aggregate(results)                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 7. HEALTH & CIRCUIT BREAKING (per-backend monitoring)       │    │
│  │    ─────────────────────────────────────                    │    │
│  │    • Health check every 30s per backend                     │    │
│  │    • Track: latency p50/p99, error_rate, success_rate       │    │
│  │    • Circuit break after 5 consecutive failures             │    │
│  │    • Auto-reconnect after 60s cooldown                      │    │
│  │    • Degraded mode: return partial results, show "X down"   │    │
│  │    • Metrics emitted to LPS for resolver awareness          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 8. CROSS-OS EVENT HANDLERS (receive + emit)                 │    │
│  │    ─────────────────────────────────────                    │    │
│  │    RECEIVE:                                                 │    │
│  │    • HealthOS → dietary restriction change → update profile │    │
│  │    • HealthOS → new allergy diagnosis → flag all recipes    │    │
│  │    • FamilyOS → chore completed → "restock" event           │    │
│  │    • FamilyOS → calendar event → suggest meal for party     │    │
│  │    • FinanceOS → budget alert → cheaper recipe alternatives │    │
│  │    • AgriOS → harvest complete → seasonal ingredient push   │    │
│  │                                                             │    │
│  │    EMIT:                                                    │    │
│  │    • food.order.placed → FinanceOS (spending)               │    │
│  │    • food.meal.planned → FamilyOS calendar                  │    │
│  │    • food.allergy.flagged → HealthOS alert                  │    │
│  │    • food.supply.low → AgriOS demand signal                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 9. AUTH & USER MANAGEMENT                                   │    │
│  │    ─────────────────────────────────────                    │    │
│  │    • OAuth2 flows for 100+ backend services                 │    │
│  │    • Token storage, refresh, revocation                     │    │
│  │    • Per-family-member dietary profiles + permissions        │    │
│  │    • Child safety: age-gated food ordering                  │    │
│  │    • Shared family payment methods across backends          │    │
│  │    • Backend connection CRUD (user controls which stores)   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 10. TESTING (unit + integration + E2E + benchmark)          │    │
│  │    ─────────────────────────────────────                    │    │
│  │    • Tool contract tests (envelope shape, dynamic enums)    │    │
│  │    • Schema normalization tests (100+ fixtures)             │    │
│  │    • Fan-out partial failure tests (mock backend outages)   │    │
│  │    • Circuit breaker behavior tests                         │    │
│  │    • Cross-OS event handler integration tests               │    │
│  │    • POC benchmark: add family.food to connector search     │    │
│  │    • Back LLM integration: "plan keto meals this week"      │    │
│  │    • Scale test: 100 backends × 15 tools = 1500 tools       │    │
│  │    • Performance: fan-out 100 backends in < 2s              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### The Stack, Layer by Layer

| Layer | What | Who Builds It | Effort |
|-------|------|--------------|--------|
| **UI** | Full native app frontend (React/Vite or Streamlit) | App developer | 40-60% of total |
| **Tools** | 12-18 capability implementations with business logic | App developer | 20-30% |
| **Connector Def** | GPS registration: tools, constitutions, schemas | App developer | 5% — the YAML is the SMALLEST part |
| **Backend Connectors** | API clients for 100+ external services | App developer (or platform team for shared backends) | 30-50% — the HEAVIEST part |
| **Schema Normalizers** | 100+ mapper functions (backend → canonical) | App developer | Embedded in backend connectors |
| **Fan-Out Engine** | asyncio.gather, partial failure, aggregation | App developer (or kernel provides primitive) | 10% if kernel provides, 20% if custom |
| **Health/Circuit** | Monitoring, circuit breaking, graceful degradation | App developer (or kernel runtime) | 5% if kernel provides, 15% if custom |
| **Cross-OS Events** | IFL event handlers (emit + receive) | App developer | 10-15% |
| **Auth** | OAuth flows, token management, user permissions | App developer (or platform auth service) | 10-15% |
| **Tests** | Unit, integration, E2E, benchmark, scale | App developer | 20-25% of total |

---

### What the Kernel Provides vs What the Developer Builds

```
┌──────────────────────────────────────────────────────────────────┐
│                     KERNEL PROVIDES                               │
│                                                                  │
│  ✅ Resolver: action_text → connector + tools + constitution     │
│  ✅ GPS: connector/capability/constitution storage               │
│  ✅ LPS: session-scoped connected_resources                      │
│  ✅ Dynamic enum injection: LPS → tool schema enums              │
│  ✅ Back LLM: reads envelope, picks tool, calls invoke_capability│
│  ✅ IFL event bus: cross-OS event routing                        │
│  ✅ invoke_capability: calls tool implementation                 │
│  ✅ Manifest admission: registers connector into GPS             │
│  ✅ Kernel boot/test harness                                     │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                     DEVELOPER BUILDS                              │
│                                                                  │
│  🔨 Native app UI (all of it)                                    │
│  🔨 Tool implementations (every invoke_capability target)        │
│  🔨 100+ backend API clients (auth, rate limit, retry, paginate) │
│  🔨 100+ schema normalizers (backend format → canonical format)  │
│  🔨 Fan-out orchestration (parallel execution, partial failure)  │
│  🔨 Health monitoring + circuit breaking per backend             │
│  🔨 Cross-OS event handlers (receive + emit, 6-12 handlers)      │
│  🔨 OAuth flows for each backend service                         │
│  🔨 Per-user backend connection management UI                    │
│  🔨 Family member profiles, permissions, dietary restrictions    │
│  🔨 Connector definition YAML (the GPS registration surface)     │
│  🔨 Constitution prose (teaching surface for Back LLM)           │
│  🔨 Full test suite (unit, integration, E2E, benchmark, scale)   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

### The Real Developer Journey: Building `family.food`

#### Phase 1 — Scaffold (Day 1-3)

```
family.food/
├── __init__.py
├── definition.py              # ← GPS registration surface (the YAML part)
├── constitution.py            # ← teaching surface prose
├── tools/
│   ├── __init__.py
│   ├── plan_meals.py          # ← business logic
│   ├── generate_list.py
│   ├── place_order.py
│   ├── price_compare.py
│   ├── track_nutrition.py
│   ├── suggest_recipes.py
│   ├── manage_dietary.py
│   └── ...10 more
├── backends/
│   ├── __init__.py
│   ├── base.py                # ← BaseBackendClient (auth, retry, circuit)
│   ├── grocery/
│   │   ├── walmart.py         # ← API client + normalizer
│   │   ├── kroger.py
│   │   ├── costco.py
│   │   └── ...15 more
│   ├── delivery/
│   │   ├── doordash.py
│   │   ├── ubereats.py
│   │   └── ...8 more
│   ├── recipes/
│   │   ├── spoonacular.py
│   │   ├── edamam.py
│   │   └── ...10 more
│   └── nutrition/
│       ├── usda_fooddata.py
│       ├── nutritionix.py
│       └── ...5 more
├── normalization/
│   ├── canonical.py           # ← canonical schema definitions
│   ├── walmart_mapper.py      # ← {itemId, productName} → {item_id, name}
│   ├── kroger_mapper.py       # ← {product_id, desc} → {item_id, name}
│   └── ...100+ more
├── events/
│   ├── handlers.py            # ← receive: HealthOS, FinanceOS, AgriOS
│   └── emitters.py            # ← emit: order.placed, meal.planned
├── ui/
│   ├── HomeView.tsx           # ← Layer 1: food timeline
│   ├── MealPlanHub.tsx        # ← Layer 2: meal plan depth
│   ├── RecipeBrowser.tsx
│   ├── GroceryList.tsx
│   ├── OrderTracker.tsx
│   └── ...components
├── tests/
│   ├── test_tools.py
│   ├── test_normalizers.py    # ← 100+ test fixtures
│   ├── test_fanout.py
│   ├── test_circuit_breaker.py
│   ├── test_events.py
│   ├── test_integration.py
│   └── test_benchmark.py
└── config/
    ├── backends.yaml           # ← backend registry (100+ entries)
    └── dietary_profiles.yaml
```

#### Phase 2 — Backend Integration (Week 1-3)

The HEAVIEST phase. For every backend:

```python
# backends/grocery/walmart.py
class WalmartBackend(BaseBackendClient):
    backend_id = "walmart-api"
    base_url = "https://api.walmart.com/v3"

    async def search_products(self, query: str, zip_code: str) -> list[CanonicalItem]:
        """Search Walmart for products, return canonical format."""
        raw = await self._request(
            "POST", "/items/search",
            json={"query": query, "zipCode": zip_code},
            auth=self._oauth_token,
        )
        # Normalize to canonical
        return [walmart_to_canonical(item) for item in raw["items"]]

    async def place_order(self, items: list[OrderItem]) -> OrderResult:
        """Place order at Walmart. Canonical input → Walmart format → canonical output."""
        walmart_items = [canonical_to_walmart(item) for item in items]
        raw = await self._request(
            "POST", "/orders",
            json={"items": walmart_items, "deliveryAddress": self.user.address},
            idempotency_key=generate_idempotency_key(),
        )
        return walmart_order_to_canonical(raw)

# normalization/walmart_mapper.py
def walmart_to_canonical(raw: dict) -> CanonicalItem:
    return CanonicalItem(
        item_id=f"walmart:{raw['itemId']}",
        name=raw.get("productName") or raw.get("name", ""),
        price=float(raw.get("price", 0)),
        currency=raw.get("currency", "USD"),
        unit=raw.get("unit", "each"),
        unit_price=float(raw.get("unitPrice", raw.get("price", 0))),
        store="Walmart",
        in_stock=raw.get("availabilityStatus") == "IN_STOCK",
        image_url=raw.get("imageUrl", ""),
        nutrition=raw.get("nutritionInfo"),
        dietary_tags=raw.get("dietaryTags", []),
        allergens=raw.get("allergens", []),
    )

# normalization/canonical.py
@dataclass
class CanonicalItem:
    item_id: str           # "{store}:{id}" — globally unique
    name: str              # "Organic Whole Milk"
    price: float           # 3.49
    currency: str          # "USD"
    unit: str              # "gallon", "oz", "each"
    unit_price: float      # price per base unit
    store: str             # "Walmart" — human readable
    in_stock: bool
    image_url: str
    nutrition: dict | None # {calories, protein_g, fat_g, carbs_g, ...}
    dietary_tags: list[str] # ["organic", "gluten-free", "keto"]
    allergens: list[str]   # ["milk", "soy"]
```

100+ of these. Each backend speaks its own dialect. Every one needs a mapper.

#### Phase 3 — Fan-Out Engine (Week 2-3)

```python
# tools/price_compare.py
async def price_compare(items: list[str], user_id: str) -> PriceComparison:
    """Fan out to ALL connected grocery backends, aggregate, rank by price."""

    # Get user's connected grocery backends
    backends = await get_connected_backends(
        user_id, app="family.food",
        backend_type="grocery",
    )  # → [WalmartBackend, KrogerBackend, CostcoBackend, ...]

    # Fan out in parallel — ALL backends queried simultaneously
    results = await asyncio.gather(*[
        backend.search_products(item, user.zip_code)
        for item in items
        for backend in backends
    ], return_exceptions=True)

    # Classify
    successes = []
    failures = []
    for i, result in enumerate(results):
        backend_idx = i % len(backends)
        if isinstance(result, Exception):
            failures.append((backends[backend_idx].backend_id, str(result)))
        else:
            successes.append(result)

    # Aggregate: group by item, sort by unit_price within each group
    by_item = defaultdict(list)
    for item in successes:
        by_item[item.name].append(item)

    comparison = {}
    for item_name, options in by_item.items():
        options.sort(key=lambda o: o.unit_price)
        comparison[item_name] = [
            {
                "store": opt.store,
                "price": opt.price,
                "unit_price": opt.unit_price,
                "in_stock": opt.in_stock,
                "backend_id": opt.item_id.split(":")[0],
            }
            for opt in options
        ]

    return PriceComparison(
        items=comparison,
        partial_failures=failures,
        total_backends=len(backends),
        healthy_backends=len(backends) - len(set(f[0] for f in failures)),
        queried_at=datetime.now().isoformat(),
    )
```

#### Phase 4 — Cross-OS Event Wiring (Week 3-4)

```python
# events/handlers.py
@ifl.subscribe("healthos.diagnosis.allergy")
async def on_new_allergy(event: AllergyEvent):
    """HealthOS diagnosed a new allergy → flag all recipes containing that allergen."""
    affected_recipes = await recipe_index.search_by_allergen(event.allergen)
    for recipe in affected_recipes:
        await flag_recipe(recipe.id, f"Contains {event.allergen} — {event.patient_name}")
    await notify_family(f"⚠️ {event.allergen} allergy diagnosed for {event.patient_name}. "
                        f"{len(affected_recipes)} recipes flagged.")

@ifl.subscribe("familyos.calendar.event_created")
async def on_party_scheduled(event: CalendarEvent):
    """Family is hosting a party → suggest meal plan, estimate grocery needs."""
    if "party" in event.title.lower() or "gathering" in event.title.lower():
        guest_count = estimate_guests(event)
        suggestions = await suggest_party_meals(guest_count, event.date)
        await emit_suggestion(suggestions, event.family_id)

@ifl.subscribe("financeos.budget.alert")
async def on_budget_alert(event: BudgetAlert):
    """FinanceOS budget tightening → suggest cheaper meal alternatives."""
    if event.category == "groceries" or event.category == "dining":
        cheaper_plans = await suggest_budget_meals(event.family_id, event.budget_remaining)
        await emit_suggestion(cheaper_plans, event.family_id)

# events/emitters.py
async def emit_order_placed(order: OrderResult, family_id: str):
    """Tell FinanceOS about the spend. Tell FamilyOS calendar about delivery window."""
    await ifl.emit("food.order.placed", {
        "family_id": family_id,
        "total": order.grand_total,
        "backends": [o.backend_id for o in order.orders],
        "delivery_window": order.earliest_delivery,
        "items_count": sum(o.item_count for o in order.orders),
    })
```

#### Phase 5 — Testing (Week 3-5)

```python
# tests/test_normalizers.py — 100+ parameterized tests
@pytest.mark.parametrize("backend,raw,expected", [
    ("walmart", {"itemId": "123", "productName": "Milk", "price": 3.49},
     CanonicalItem(item_id="walmart:123", name="Milk", price=3.49, ...)),
    ("kroger", {"product_id": "456", "desc": "Milk", "current_price": 3.29},
     CanonicalItem(item_id="kroger:456", name="Milk", price=3.29, ...)),
    ("doordash", {"item.external_id": "789", "item.name": "Pizza",
                  "item.price_display_string": "$12.99"},
     CanonicalItem(item_id="doordash:789", name="Pizza", price=12.99, ...)),
    # ... 100+ more
])
def test_normalize(backend, raw, expected):
    normalizer = get_normalizer(backend)
    result = normalizer(raw)
    assert result == expected

# tests/test_fanout.py — partial failure tolerance
async def test_price_compare_with_2_of_5_backends_down():
    """When 2 backends fail, we still get results from 3."""
    with mock_backends(healthy=["walmart", "kroger", "aldi"],
                       down=["costco", "target"]):
        result = await price_compare(["milk"], user_id="test-user")
        assert result.total_backends == 5
        assert result.healthy_backends == 3
        assert len(result.partial_failures) == 2
        assert len(result.items["milk"]) >= 3  # got results from healthy ones

# tests/test_benchmark.py — POC integration
def test_family_food_connector_resolves():
    """family.food must resolve as top result for food-related queries."""
    resolver = ConnectorResolver(gps)
    hits = resolver.search("plan keto meals this week")
    assert hits[0].connector_id == "family.food"
    assert hits[0].score > 0.70

def test_family_food_in_envelope():
    """Resolution envelope contains food tools with dynamic enum."""
    envelope = await resolve("order pizza for dinner tonight")
    assert envelope.connector.connector_id == "family.food"
    # place_delivery_order tool should have dynamic backend_id enum
    order_tool = next(t for t in envelope.tools
                      if t.capability_name == "tool.execute.food.place_delivery_order")
    assert "backend_id" in [i.name for i in order_tool.required_inputs]
    backend_input = next(i for i in order_tool.required_inputs if i.name == "backend_id")
    assert backend_input.enum == ["doordash-api", "ubereats-api"]  # ← injected from LPS
```

---

### The Point

That single `connector_id: "family.food"` YAML block? That's **5%** of what a developer builds. It's just the GPS registration surface — the thing the resolver indexes. Behind it is:

- **100+ backend API clients** with auth, retry, pagination, rate limiting
- **100+ schema normalizers** translating every backend dialect to canonical
- **12-18 tool implementations** with real business logic
- **Fan-out orchestration** handling 100 parallel API calls with partial failure
- **6-12 cross-OS event handlers** receiving from HealthOS, FinanceOS, AgriOS, FamilyOS
- **Health monitoring + circuit breaking** for every backend
- **Full UI**: meal planner, recipe browser, grocery list, order tracker, nutrition dashboard
- **OAuth flows** for every backend service the user can connect
- **Comprehensive test suite**: unit, normalizer fixtures, fan-out, circuit breaker, integration, benchmark

The kernel gives you the resolver, the envelope, the event bus, and the execution harness. Everything else — the app, the backends, the normalization, the UI, the business logic, the tests — that's on the developer.

And they do this for **every domain app** in every OS. `family.shopping`, `family.calendar`, `family.chores`, `health.records`, `health.medications`, `finance.accounts`, `enterprise.hr`, `agrios.crops`, `pharmaos.fulfillment` — each one is this much work.

---

## Dynamic Enum Injection — Infrastructure Prerequisites (2026-06-17)

**Status:** Resolver-side code is wired. Native app infrastructure is the missing dependency.

### Architecture Flow

```
USER connects backend in UI
  → Native App Inbound API (OAuth flow)
    → Writes to LPS connected_resources: {session_id, connector_id, backend_id, label, status}
      → Resolver _inject_session_aware_enums reads LPS at resolution time
        → Injects live enum values into tool schemas (enum + enum_labels)
          → Back LLM sees dynamic enums in resolution envelope
            → Back LLM passes backend_id in invoke_capability params
              → Native app routes to correct backend API
```

### What Already Exists (resolver-side, wired and working)

| Component | File | Status |
|-----------|------|--------|
| LPS `connected_resources` table | `k1/fabric/stores/local_projection_store.py:55` | Schema exists |
| LPS `get_connected_backends()` | `k1/fabric/stores/local_projection_store.py:177` | Read path works |
| GPS `connector_backends` table | `k1/fabric/stores/global_projection_store.py:713` | Schema exists, EMPTY |
| `_inject_session_aware_enums()` | `k1/fabric/resolver/situated_resolver.py:134` | Implemented, finds nothing to inject |
| `enum_source` marker on tools | All 6 definition.py files | 0 of 52 actions have it |
| `FieldSpec.enum_source` field | `k1/tools/family/definition.py` | Not in model |
| Back prompt enum instruction | `k1/concierge/prompt/back_prompt.py` | Not mentioned |

### What Must Be Built (when native app backend integration begins)

#### 1. FieldSpec model extension (`k1/tools/family/definition.py`)

Add three fields to `FieldSpec`:

- `enum_source: str | None = None` — marker for dynamic enums, value `"lps.connected_backends"`
- `enum_values: list[str] | None = None` — static enum values (for non-dynamic enums like visibility bands)
- `enum_labels: list[str] | None = None` — human-readable labels matching enum values

#### 2. Tool definition markers (each connector's `definition.py`)

For any tool input that selects a backend, add `enum_source`:

```python
FieldSpec(
    name="backend_id",
    type="string",
    required=True,
    description="Which backend to use. Pick from the enum list.",
    enum_source="lps.connected_backends",
)
```

Connectors that will need this when backends exist:

- `family.calendar.connect_feed` — `feed_source` (google|outlook|classroom|apple)
- `family.shopping` — future `backend_id` on place_order, price_check
- `family.tasks` — future `backend_id` on create_task (sync to Todoist|TickTick)
- `family.reminders` — future `backend_id` on set_reminder

#### 3. GPS `connector_backends` population

During bootstrap/admission, register known backend slots per connector:

```python
gps.upsert_connector_backend(
    connector_id="family.calendar",
    backend_id="google-calendar-api",
    backend_label="Google Calendar",
)
```

This tells the resolver which backends a connector CAN use, so it can filter LPS results to only valid backends for that connector.

#### 4. Native App Inbound API — LPS write path (OWNED BY NATIVE APP, NOT RESOLVER)

This is the heaviest piece. Must implement:

- OAuth2 flow for each backend service (Google, Outlook, Walmart, etc.)
- Encrypted token storage, refresh, revocation
- Backend connection CRUD via user-facing UI
- Write to LPS `connected_resources` on connect/disconnect:

  ```python
  lps.upsert_connected_resource({
      session_id=session_id,
      connector_id="family.calendar",
      backend_id="google-calendar-api",
      label="alex@gmail.com",
      status="active",
  })
  ```

- Health check per backend on connect
- Backend disconnection + cleanup

#### 5. Manifest translator propagation

When building tool dicts for the resolution envelope, propagate enum metadata from FieldSpec into the dict so `_inject_session_aware_enums` can find it:

```python
if field.enum_source:
    tool_input["enum_source"] = field.enum_source
if field.enum_values:
    tool_input["enum"] = field.enum_values
if field.enum_labels:
    tool_input["enum_labels"] = field.enum_labels
```

#### 6. Back prompt instruction (`back_prompt.py`)

Add to the EXECUTION PROTOCOL section:

```
ENUM FIELDS: Some tool inputs have an "enum" field with valid values and
"enum_labels" with human-readable names.  When the user says "order from
Walmart", look at enum_labels to find "Walmart", then use the corresponding
enum value (e.g., "walmart-api") as the backend_id.  Never guess backend
IDs — only use values from the enum list.
```

### Why Current Connectors Don't Need This Yet

The 6 current FamilyOS connectors are LOCAL-ONLY (SQLite-backed). They have no external backend connections:

- `calendar.connect_feed` is a stub — writes a local record, no real OAuth or API connection
- Shopping, tasks, reminders, chores — all operate on local data only
- No connector has a `backend_id` field in any tool

This infrastructure becomes critical when:

- `family.shopping` gains `place_order` with real Walmart/Instacart/Target backends
- `family.calendar` gains real Google/Outlook/Apple Calendar sync
- `family.tasks` gains sync to Todoist/TickTick/Asana
- New connectors like `family.food`, `family.money` are created with multi-backend fan-out

### Current Working State (2026-06-17)

The Back LLM flow works correctly for all 6 local-only connectors:

```
resolve_situation → family.calendar (0.48) ✅
  → invoke_capability: tool.read.calendar.list_events ✅
  → invoke_capability: tool.execute.calendar.create_event ✅
  → invoke_capability: tool.read.calendar.get_event ✅
  → submit_result ✅
```

The dynamic enum injection is dead code that will activate automatically when:

1. A native app populates LPS with connected backends (step 4 above)
2. Tool definitions have `enum_source` markers (step 2 above)
