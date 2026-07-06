"""
POC v2: Cross-OS Benchmark Queries — 120 queries across 6 tiers
=================================================================
Tests native-app routing accuracy across 33 apps in 5 OS domains.

Tiers:
  Tier 1 — Single-OS FamilyOS (25 queries)
           No cross-OS ambiguity. Baseline accuracy.
  Tier 2 — Cross-OS Health vs Family (25 queries)
           The REAL dragon: is this a health app or a family app?
  Tier 3 — Cross-OS Finance vs Family (20 queries)
           Money queries that could route to FamilyOS or FinanceOS.
  Tier 4 — Cross-OS Pharma vs Health vs Family (15 queries)
           Pharmacy queries — fulfillment, medication, or reminder?
  Tier 5 — EnterpriseOS Routing (15 queries)
           Work-related queries distinct from family tasks.
  Tier 6 — Backend-Name Mention (20 queries)
           User mentions a backend brand. Must NOT route to backend.

Each query record:
  {
    "id": str,
    "utterance": str,           # raw user text
    "expected_native_app": str, # correct routing target
    "active_os_set": set[str],  # which OS domains are active
    "tier": str,
    "rationale": str,           # why this is the expected answer
    "backend_hints": list[str], # backend names mentioned (for Tier 6)
  }

Usage:
  python scripts/poc_v2/bench_queries.py --validate  # check all queries
  python scripts/poc_v2/bench_queries.py --list      # print summary
"""

from __future__ import annotations

from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# Tier 1: Single-OS FamilyOS (25 queries)
# ═══════════════════════════════════════════════════════════════════════════

TIER1_FAMILY: list[dict[str, Any]] = [
    # ── Calendar ──
    {
        "id": "fam-cal-01",
        "utterance": "what does my calendar look like this week",
        "expected_native_app": "family.calendar",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Clear calendar intent — schedule overview",
        "backend_hints": [],
    },
    {
        "id": "fam-cal-02",
        "utterance": "show me my appointments for tomorrow",
        "expected_native_app": "family.calendar",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Appointment listing — calendar domain",
        "backend_hints": [],
    },
    {
        "id": "fam-cal-03",
        "utterance": "create a dentist appointment for Riley on Monday at 3pm",
        "expected_native_app": "family.calendar",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Create event — calendar",
        "backend_hints": [],
    },
    {
        "id": "fam-cal-04",
        "utterance": "add Riley's soccer practice Saturday 9am to 11am",
        "expected_native_app": "family.calendar",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Add recurring event — calendar",
        "backend_hints": [],
    },
    # ── Shopping ──
    {
        "id": "fam-shop-01",
        "utterance": "add milk and eggs to the grocery list",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Add items to shopping list — clear shopping intent",
        "backend_hints": [],
    },
    {
        "id": "fam-shop-02",
        "utterance": "what's on my shopping list right now",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "List shopping items — shopping",
        "backend_hints": [],
    },
    {
        "id": "fam-shop-03",
        "utterance": "compare prices on diapers",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Price comparison — shopping domain",
        "backend_hints": [],
    },
    {
        "id": "fam-shop-04",
        "utterance": "mark eggs as bought on the list",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Check off item — shopping",
        "backend_hints": [],
    },
    # ── Tasks ──
    {
        "id": "fam-task-01",
        "utterance": "did Riley finish her homework",
        "expected_native_app": "family.tasks",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Task status check — tasks domain",
        "backend_hints": [],
    },
    {
        "id": "fam-task-02",
        "utterance": "assign the science project to Emma",
        "expected_native_app": "family.tasks",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Assign task to family member — tasks",
        "backend_hints": [],
    },
    {
        "id": "fam-task-03",
        "utterance": "what tasks are due this weekend",
        "expected_native_app": "family.tasks",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Task listing — tasks domain",
        "backend_hints": [],
    },
    {
        "id": "fam-task-04",
        "utterance": "mark the book report as done",
        "expected_native_app": "family.tasks",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Complete task — tasks",
        "backend_hints": [],
    },
    # ── Reminders ──
    {
        "id": "fam-rem-01",
        "utterance": "set a reminder to call Mom at 3pm",
        "expected_native_app": "family.reminders",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Time-based reminder — reminders domain",
        "backend_hints": [],
    },
    {
        "id": "fam-rem-02",
        "utterance": "remind me to water the plants every Tuesday",
        "expected_native_app": "family.reminders",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Recurring reminder — reminders",
        "backend_hints": [],
    },
    {
        "id": "fam-rem-03",
        "utterance": "what reminders do I have today",
        "expected_native_app": "family.reminders",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "List reminders — reminders",
        "backend_hints": [],
    },
    # ── Chores ──
    {
        "id": "fam-chore-01",
        "utterance": "who's supposed to do the dishes tonight",
        "expected_native_app": "family.chores",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Chore assignment query — chores domain",
        "backend_hints": [],
    },
    {
        "id": "fam-chore-02",
        "utterance": "mark the lawn mowing as done",
        "expected_native_app": "family.chores",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Complete chore — chores",
        "backend_hints": [],
    },
    {
        "id": "fam-chore-03",
        "utterance": "rotate the bathroom cleaning schedule",
        "expected_native_app": "family.chores",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Chore rotation — chores",
        "backend_hints": [],
    },
    {
        "id": "fam-chore-04",
        "utterance": "what chores does Riley have this week",
        "expected_native_app": "family.chores",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Chore assignment view — chores",
        "backend_hints": [],
    },
    # ── Settings ──
    {
        "id": "fam-set-01",
        "utterance": "turn off automatic chore rotation",
        "expected_native_app": "family.family_settings",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Feature toggle — settings domain",
        "backend_hints": [],
    },
    {
        "id": "fam-set-02",
        "utterance": "change Emma's permission to not allow shopping approvals",
        "expected_native_app": "family.family_settings",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Permission management — settings",
        "backend_hints": [],
    },
    # ── Edge cases within FamilyOS ──
    {
        "id": "fam-edge-01",
        "utterance": "pick up milk on the way home",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Implied shopping item — shopping",
        "backend_hints": [],
    },
    {
        "id": "fam-edge-02",
        "utterance": "I need to buy groceries for the party Saturday",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Shopping for event — shopping (not calendar, the event exists already)",
        "backend_hints": [],
    },
    {
        "id": "fam-edge-03",
        "utterance": "don't let me forget to pack lunches tonight",
        "expected_native_app": "family.reminders",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Reminder phrasing — reminders, not tasks (implied one-time nudge)",
        "backend_hints": [],
    },
    {
        "id": "fam-edge-04",
        "utterance": "what are we running low on",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier1_family",
        "rationale": "Stock check — shopping domain",
        "backend_hints": [],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Tier 2: Cross-OS Health vs Family (25 queries)
# ═══════════════════════════════════════════════════════════════════════════

TIER2_HEALTH: list[dict[str, Any]] = [
    # ── Medication vs Reminder ──
    {
        "id": "cross-h-01",
        "utterance": "remind me to take my blood pressure medication",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Medication reminder — medications manages dose tracking and adherence, not generic reminders",
        "backend_hints": [],
    },
    {
        "id": "cross-h-02",
        "utterance": "I need to refill my Lisinopril prescription",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Prescription refill — medication management",
        "backend_hints": [],
    },
    {
        "id": "cross-h-03",
        "utterance": "set a daily reminder for my evening pills",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Medication-specific reminder — medication domain, not generic reminder",
        "backend_hints": [],
    },
    {
        "id": "cross-h-04",
        "utterance": "check if my amoxicillin interacts with ibuprofen",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Drug interaction check — medication domain only",
        "backend_hints": [],
    },
    {
        "id": "cross-h-05",
        "utterance": "I missed my dose this morning what should I do",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Missed dose guidance — medication domain",
        "backend_hints": [],
    },
    # ── Appointment vs Calendar ──
    {
        "id": "cross-h-06",
        "utterance": "what time is my doctor appointment tomorrow",
        "expected_native_app": "health.appointments",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Healthcare appointment — appointments domain, not generic calendar",
        "backend_hints": [],
    },
    {
        "id": "cross-h-07",
        "utterance": "schedule a telehealth visit with Dr. Chen",
        "expected_native_app": "health.appointments",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Telehealth booking — health appointments",
        "backend_hints": [],
    },
    {
        "id": "cross-h-08",
        "utterance": "find a dermatologist near me that takes my insurance",
        "expected_native_app": "health.appointments",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Provider search — appointments domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-09",
        "utterance": "I need to reschedule my annual physical",
        "expected_native_app": "health.appointments",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Reschedule medical appointment — health appointments",
        "backend_hints": [],
    },
    # ── Vitals ──
    {
        "id": "cross-h-10",
        "utterance": "check my blood pressure",
        "expected_native_app": "health.vitals",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Vital sign check — vitals domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-11",
        "utterance": "how did I sleep last night",
        "expected_native_app": "health.vitals",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Sleep data query — vitals domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-12",
        "utterance": "has my resting heart rate changed this month",
        "expected_native_app": "health.vitals",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Heart rate trend — vitals domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-13",
        "utterance": "I've only walked 2000 steps today",
        "expected_native_app": "health.vitals",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Activity metric — vitals domain",
        "backend_hints": [],
    },
    # ── Lab Results ──
    {
        "id": "cross-h-14",
        "utterance": "show me my blood work results from last week",
        "expected_native_app": "health.lab_results",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Lab result query — lab_results domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-15",
        "utterance": "what was my cholesterol level at my last checkup",
        "expected_native_app": "health.lab_results",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Lab value query — lab_results domain",
        "backend_hints": [],
    },
    # ── Insurance ──
    {
        "id": "cross-h-16",
        "utterance": "does my insurance cover an MRI",
        "expected_native_app": "health.insurance",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Coverage check — health insurance domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-17",
        "utterance": "find an in-network cardiologist near me",
        "expected_native_app": "health.insurance",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "In-network provider search — health insurance",
        "backend_hints": [],
    },
    # ── Records ──
    {
        "id": "cross-h-18",
        "utterance": "pull up my full medical history",
        "expected_native_app": "health.records",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Patient history — records domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-19",
        "utterance": "what vaccinations does Riley need for school",
        "expected_native_app": "health.records",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Immunization records — records domain (not medications)",
        "backend_hints": [],
    },
    # ── Caregiving ──
    {
        "id": "cross-h-20",
        "utterance": "check on Mom's care plan for this week",
        "expected_native_app": "health.caregiving",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Care plan check — caregiving domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-21",
        "utterance": "update Dad's emergency contact information",
        "expected_native_app": "health.caregiving",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Emergency contact management — caregiving",
        "backend_hints": [],
    },
    # ── Edge Cases ──
    {
        "id": "cross-h-22",
        "utterance": "I've been feeling tired and my BP is high",
        "expected_native_app": "health.vitals",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Symptom + vital sign — vitals for BP tracking, not records",
        "backend_hints": [],
    },
    {
        "id": "cross-h-23",
        "utterance": "set up a medication schedule that works with my work hours",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Medication schedule — medications domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-24",
        "utterance": "the doctor ordered new labs where do I go",
        "expected_native_app": "health.lab_results",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Lab order + location — lab_results domain",
        "backend_hints": [],
    },
    {
        "id": "cross-h-25",
        "utterance": "can I see a specialist without a referral",
        "expected_native_app": "health.insurance",
        "active_os_set": {"family", "health"},
        "tier": "tier2_health",
        "rationale": "Insurance coverage question — health insurance",
        "backend_hints": [],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Tier 3: Cross-OS Finance vs Family (20 queries)
# ═══════════════════════════════════════════════════════════════════════════

TIER3_FINANCE: list[dict[str, Any]] = [
    {
        "id": "cross-f-01",
        "utterance": "we're over budget on groceries this month",
        "expected_native_app": "finance.budgeting",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Budget tracking — finance, not shopping",
        "backend_hints": [],
    },
    {
        "id": "cross-f-02",
        "utterance": "how much did we spend on dining out last month",
        "expected_native_app": "finance.budgeting",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Spending analysis — finance budgeting",
        "backend_hints": [],
    },
    {
        "id": "cross-f-03",
        "utterance": "what's our savings goal progress",
        "expected_native_app": "finance.budgeting",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Savings goal — finance budgeting",
        "backend_hints": [],
    },
    {
        "id": "cross-f-04",
        "utterance": "did my paycheck hit the account yet",
        "expected_native_app": "finance.accounts",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Account balance check — finance accounts",
        "backend_hints": [],
    },
    {
        "id": "cross-f-05",
        "utterance": "how are my investments doing this quarter",
        "expected_native_app": "finance.investing",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Portfolio check — finance investing",
        "backend_hints": [],
    },
    {
        "id": "cross-f-06",
        "utterance": "compare mortgage refinance rates",
        "expected_native_app": "finance.loans",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Refinance — loans domain",
        "backend_hints": [],
    },
    {
        "id": "cross-f-07",
        "utterance": "I need to file my tax return",
        "expected_native_app": "finance.taxes",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Tax filing — finance taxes",
        "backend_hints": [],
    },
    {
        "id": "cross-f-08",
        "utterance": "is our home insurance up for renewal",
        "expected_native_app": "finance.insurance",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Home insurance — finance insurance, not health",
        "backend_hints": [],
    },
    {
        "id": "cross-f-09",
        "utterance": "set aside $200 for Emma's college fund",
        "expected_native_app": "finance.investing",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Investment goal — finance investing",
        "backend_hints": [],
    },
    {
        "id": "cross-f-10",
        "utterance": "how much is left on my car loan",
        "expected_native_app": "finance.loans",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Loan balance — finance loans",
        "backend_hints": [],
    },
    {
        "id": "cross-f-11",
        "utterance": "transfer $500 from savings to checking",
        "expected_native_app": "finance.accounts",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Fund transfer — finance accounts",
        "backend_hints": [],
    },
    {
        "id": "cross-f-12",
        "utterance": "what's my current net worth",
        "expected_native_app": "finance.accounts",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Net worth — finance accounts aggregation",
        "backend_hints": [],
    },
    {
        "id": "cross-f-13",
        "utterance": "are there any bills I can negotiate down",
        "expected_native_app": "finance.budgeting",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Bill negotiation — finance budgeting",
        "backend_hints": [],
    },
    {
        "id": "cross-f-14",
        "utterance": "track my business expenses for tax season",
        "expected_native_app": "finance.taxes",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Tax expense tracking — finance taxes",
        "backend_hints": [],
    },
    {
        "id": "cross-f-15",
        "utterance": "compare auto insurance quotes",
        "expected_native_app": "finance.insurance",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Auto insurance — finance insurance, not health",
        "backend_hints": [],
    },
    {
        "id": "cross-f-16",
        "utterance": "should I pay off my student loan early",
        "expected_native_app": "finance.loans",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Loan payoff analysis — finance loans",
        "backend_hints": [],
    },
    {
        "id": "cross-f-17",
        "utterance": "what's my total monthly spending on subscriptions",
        "expected_native_app": "finance.budgeting",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Spending categorization — finance budgeting",
        "backend_hints": [],
    },
    {
        "id": "cross-f-18",
        "utterance": "did the IRS accept my tax filing",
        "expected_native_app": "finance.taxes",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Tax filing status — finance taxes",
        "backend_hints": [],
    },
    {
        "id": "cross-f-19",
        "utterance": "how much home can I afford with my salary",
        "expected_native_app": "finance.loans",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Affordability analysis — finance loans",
        "backend_hints": [],
    },
    {
        "id": "cross-f-20",
        "utterance": "my car insurance premium went up again",
        "expected_native_app": "finance.insurance",
        "active_os_set": {"family", "finance"},
        "tier": "tier3_finance",
        "rationale": "Auto insurance — finance insurance domain",
        "backend_hints": [],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Tier 4: Cross-OS Pharma vs Health vs Family (15 queries)
# ═══════════════════════════════════════════════════════════════════════════

TIER4_PHARMA: list[dict[str, Any]] = [
    {
        "id": "cross-p-01",
        "utterance": "Walgreens says my prescription is ready for pickup",
        "expected_native_app": "pharmaos.fulfillment",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Fulfillment status — pharmacy fulfillment, not medication management",
        "backend_hints": ["walgreens"],
    },
    {
        "id": "cross-p-02",
        "utterance": "is my Lipitor ready at the pharmacy yet",
        "expected_native_app": "pharmaos.fulfillment",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Fulfillment status check — pharmaos fulfillment",
        "backend_hints": [],
    },
    {
        "id": "cross-p-03",
        "utterance": "Dr. Chen sent a new prescription to CVS",
        "expected_native_app": "pharmaos.fulfillment",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "New prescription receipt at pharmacy — pharmaos fulfillment",
        "backend_hints": ["cvs"],
    },
    {
        "id": "cross-p-04",
        "utterance": "how much will this prescription cost with my insurance",
        "expected_native_app": "pharmaos.insurance",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Insurance adjudication at pharmacy — pharmaos insurance",
        "backend_hints": [],
    },
    {
        "id": "cross-p-05",
        "utterance": "refill all my active prescriptions",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Patient-side refill — health medications, not pharma fulfillment",
        "backend_hints": [],
    },
    {
        "id": "cross-p-06",
        "utterance": "what time does Walgreens close today",
        "expected_native_app": "pharmaos.customer",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Pharmacy info — pharmaos customer communication",
        "backend_hints": ["walgreens"],
    },
    {
        "id": "cross-p-07",
        "utterance": "remind me to pick up my prescription after work",
        "expected_native_app": "family.reminders",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Simple time reminder — family reminders. Prescription context is incidental.",
        "backend_hints": [],
    },
    {
        "id": "cross-p-08",
        "utterance": "does my amoxicillin interact with lisinopril",
        "expected_native_app": "health.medications",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Drug interaction check — health medications",
        "backend_hints": [],
    },
    {
        "id": "cross-p-09",
        "utterance": "the pharmacy said my prior authorization was denied",
        "expected_native_app": "pharmaos.insurance",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Prior auth denial — pharmaos insurance adjudication",
        "backend_hints": [],
    },
    {
        "id": "cross-p-10",
        "utterance": "text me when my medication is ready",
        "expected_native_app": "pharmaos.customer",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Patient notification preference — pharmaos customer",
        "backend_hints": [],
    },
    {
        "id": "cross-p-11",
        "utterance": "track my compounding formula for Emma's specialty medication",
        "expected_native_app": "pharmaos.compounding",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Compounding formula — pharmaos compounding",
        "backend_hints": [],
    },
    {
        "id": "cross-p-12",
        "utterance": "check inventory for amoxicillin 500mg",
        "expected_native_app": "pharmaos.inventory",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Inventory check — pharmaos inventory",
        "backend_hints": [],
    },
    {
        "id": "cross-p-13",
        "utterance": "log this controlled substance dispensing",
        "expected_native_app": "pharmaos.compliance",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "DEA controlled substance tracking — pharmaos compliance",
        "backend_hints": [],
    },
    {
        "id": "cross-p-14",
        "utterance": "the vaccine shipment needs cold chain monitoring",
        "expected_native_app": "pharmaos.inventory",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Cold chain — pharmaos inventory",
        "backend_hints": [],
    },
    {
        "id": "cross-p-15",
        "utterance": "document the pharmacist counseling I gave Mrs. Garcia",
        "expected_native_app": "pharmaos.customer",
        "active_os_set": {"family", "health", "pharma"},
        "tier": "tier4_pharma",
        "rationale": "Counseling documentation — pharmaos customer",
        "backend_hints": [],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Tier 5: EnterpriseOS Routing (15 queries)
# ═══════════════════════════════════════════════════════════════════════════

TIER5_ENTERPRISE: list[dict[str, Any]] = [
    {
        "id": "ent-01",
        "utterance": "request PTO for June 20 through 24",
        "expected_native_app": "enterprise.hr",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Leave request — enterprise HR",
        "backend_hints": [],
    },
    {
        "id": "ent-02",
        "utterance": "how many PTO days do I have left",
        "expected_native_app": "enterprise.hr",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Leave balance — enterprise HR",
        "backend_hints": [],
    },
    {
        "id": "ent-03",
        "utterance": "deploy the auth service to staging",
        "expected_native_app": "enterprise.devops",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Deployment — enterprise DevOps",
        "backend_hints": [],
    },
    {
        "id": "ent-04",
        "utterance": "who's on call this weekend",
        "expected_native_app": "enterprise.devops",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "On-call schedule — enterprise DevOps",
        "backend_hints": [],
    },
    {
        "id": "ent-05",
        "utterance": "create a ticket for the login page bug",
        "expected_native_app": "enterprise.project_mgmt",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Bug ticket — enterprise project management",
        "backend_hints": [],
    },
    {
        "id": "ent-06",
        "utterance": "what's the status of the Q3 planning epic",
        "expected_native_app": "enterprise.project_mgmt",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Epic status — enterprise project management",
        "backend_hints": [],
    },
    {
        "id": "ent-07",
        "utterance": "send the onboarding guide to the new hire",
        "expected_native_app": "enterprise.documentation",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Document sharing — enterprise documentation",
        "backend_hints": [],
    },
    {
        "id": "ent-08",
        "utterance": "message the eng-team channel about the outage",
        "expected_native_app": "enterprise.communication",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Team messaging — enterprise communication",
        "backend_hints": [],
    },
    {
        "id": "ent-09",
        "utterance": "update the Acme Corp deal in Salesforce",
        "expected_native_app": "enterprise.crm",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "CRM deal update — enterprise CRM",
        "backend_hints": [],
    },
    {
        "id": "ent-10",
        "utterance": "run the Q2 payroll for all employees",
        "expected_native_app": "enterprise.payroll",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Payroll run — enterprise payroll",
        "backend_hints": [],
    },
    {
        "id": "ent-11",
        "utterance": "my laptop won't connect to the VPN",
        "expected_native_app": "enterprise.it",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "IT support — enterprise IT",
        "backend_hints": [],
    },
    {
        "id": "ent-12",
        "utterance": "provision a new MacBook for the designer starting Monday",
        "expected_native_app": "enterprise.it",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Asset provisioning — enterprise IT",
        "backend_hints": [],
    },
    {
        "id": "ent-13",
        "utterance": "is the CI build passing on the main branch",
        "expected_native_app": "enterprise.devops",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "CI status — enterprise DevOps",
        "backend_hints": [],
    },
    {
        "id": "ent-14",
        "utterance": "find the sales playbook document",
        "expected_native_app": "enterprise.documentation",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Document search — enterprise documentation",
        "backend_hints": [],
    },
    {
        "id": "ent-15",
        "utterance": "schedule a Zoom meeting with the design team at 2pm",
        "expected_native_app": "enterprise.communication",
        "active_os_set": {"enterprise"},
        "tier": "tier5_enterprise",
        "rationale": "Meeting scheduling — enterprise communication (not family calendar in enterprise context)",
        "backend_hints": [],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Tier 6: Backend-Name Mention — does NOT change routing (20 queries)
# ═══════════════════════════════════════════════════════════════════════════

TIER6_BACKEND: list[dict[str, Any]] = [
    # ── Shopping backends ──
    {
        "id": "back-01",
        "utterance": "order milk from Walmart",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Walmart is a backend to family.shopping, not a routing target",
        "backend_hints": ["walmart"],
    },
    {
        "id": "back-02",
        "utterance": "add eggs to my Costco list",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Costco is a backend — shopping list management",
        "backend_hints": ["costco"],
    },
    {
        "id": "back-03",
        "utterance": "compare Kroger vs Aldi prices on chicken breast",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Price comparison across backends — still shopping",
        "backend_hints": ["kroger", "aldi"],
    },
    {
        "id": "back-04",
        "utterance": "did my Amazon Fresh order ship yet",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Order status for a backend — still shopping",
        "backend_hints": ["amazon fresh"],
    },
    {
        "id": "back-05",
        "utterance": "add paper towels from Target to the cart",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Add to cart from specific retailer — shopping",
        "backend_hints": ["target"],
    },
    {
        "id": "back-06",
        "utterance": "order dinner from DoorDash tonight",
        "expected_native_app": "family.shopping",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Food delivery — DoorDash is a backend to shopping",
        "backend_hints": ["doordash"],
    },
    # ── Task backends ──
    {
        "id": "back-07",
        "utterance": "sync my Todoist tasks to the family board",
        "expected_native_app": "family.tasks",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Todoist is a task backend, not a competing task app",
        "backend_hints": ["todoist"],
    },
    {
        "id": "back-08",
        "utterance": "add this Trello card to our family tasks",
        "expected_native_app": "family.tasks",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Trello backend item → family tasks",
        "backend_hints": ["trello"],
    },
    # ── Calendar backends ──
    {
        "id": "back-09",
        "utterance": "add this Google Calendar event to the family schedule",
        "expected_native_app": "family.calendar",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Google Calendar is a calendar backend, not a competing app",
        "backend_hints": ["google calendar"],
    },
    {
        "id": "back-10",
        "utterance": "sync my Outlook work calendar with family events",
        "expected_native_app": "family.calendar",
        "active_os_set": {"family"},
        "tier": "tier6_backend",
        "rationale": "Outlook is a calendar backend",
        "backend_hints": ["outlook"],
    },
    # ── Health backends ──
    {
        "id": "back-11",
        "utterance": "my Fitbit says I slept 5 hours last night",
        "expected_native_app": "health.vitals",
        "active_os_set": {"health", "family"},
        "tier": "tier6_backend",
        "rationale": "Fitbit is a wearable data source for vitals, not a routing target",
        "backend_hints": ["fitbit"],
    },
    {
        "id": "back-12",
        "utterance": "log this meal in MyFitnessPal",
        "expected_native_app": "health.vitals",
        "active_os_set": {"health", "family"},
        "tier": "tier6_backend",
        "rationale": "MyFitnessPal is a nutrition data source — vitals",
        "backend_hints": ["myfitnesspal"],
    },
    {
        "id": "back-13",
        "utterance": "the Apple Watch shows my heart rate at 72",
        "expected_native_app": "health.vitals",
        "active_os_set": {"health", "family"},
        "tier": "tier6_backend",
        "rationale": "Apple Watch is a wearable backend for vitals",
        "backend_hints": ["apple watch"],
    },
    {
        "id": "back-14",
        "utterance": "pull my lab results from LabCorp",
        "expected_native_app": "health.lab_results",
        "active_os_set": {"health", "family"},
        "tier": "tier6_backend",
        "rationale": "LabCorp is a lab backend — still lab_results",
        "backend_hints": ["labcorp"],
    },
    # ── Finance backends ──
    {
        "id": "back-15",
        "utterance": "connect my Venmo to the family finance dashboard",
        "expected_native_app": "finance.accounts",
        "active_os_set": {"finance", "family"},
        "tier": "tier6_backend",
        "rationale": "Venmo is a payment backend — finance accounts",
        "backend_hints": ["venmo"],
    },
    {
        "id": "back-16",
        "utterance": "deposit this check with Chase mobile",
        "expected_native_app": "finance.accounts",
        "active_os_set": {"finance", "family"},
        "tier": "tier6_backend",
        "rationale": "Chase is a bank backend — finance accounts",
        "backend_hints": ["chase"],
    },
    {
        "id": "back-17",
        "utterance": "import my Robinhood portfolio",
        "expected_native_app": "finance.investing",
        "active_os_set": {"finance", "family"},
        "tier": "tier6_backend",
        "rationale": "Robinhood is a brokerage backend — finance investing",
        "backend_hints": ["robinhood"],
    },
    # ── Pharma backends ──
    {
        "id": "back-18",
        "utterance": "did CVS receive my new prescription from Dr. Chen",
        "expected_native_app": "pharmaos.fulfillment",
        "active_os_set": {"pharma", "health", "family"},
        "tier": "tier6_backend",
        "rationale": "CVS is a pharmacy backend — pharma fulfillment",
        "backend_hints": ["cvs"],
    },
    # ── Enterprise backends ──
    {
        "id": "back-19",
        "utterance": "deploy to AWS us-east-1",
        "expected_native_app": "enterprise.devops",
        "active_os_set": {"enterprise"},
        "tier": "tier6_backend",
        "rationale": "AWS is a cloud backend — enterprise DevOps",
        "backend_hints": ["aws"],
    },
    {
        "id": "back-20",
        "utterance": "the Okta integration is failing for new hires",
        "expected_native_app": "enterprise.it",
        "active_os_set": {"enterprise"},
        "tier": "tier6_backend",
        "rationale": "Okta is an access management backend — enterprise IT",
        "backend_hints": ["okta"],
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Master corpus
# ═══════════════════════════════════════════════════════════════════════════

ALL_QUERIES: list[dict[str, Any]] = (
    TIER1_FAMILY + TIER2_HEALTH + TIER3_FINANCE + TIER4_PHARMA + TIER5_ENTERPRISE + TIER6_BACKEND
)

# Ensure all active_os_set values are actual Python sets (JSON serializable as lists)
for _q in ALL_QUERIES:
    _q["active_os_set"] = set(_q["active_os_set"])


def get_queries_by_tier() -> dict[str, list[dict[str, Any]]]:
    """Group queries by tier."""
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for q in ALL_QUERIES:
        by_tier.setdefault(q["tier"], []).append(q)
    return by_tier


def validate(all_native_app_ids: set[str]) -> list[str]:
    """Validate all queries. Returns list of issues (empty = clean)."""
    issues: list[str] = []

    valid_tiers = {
        "tier1_family",
        "tier2_health",
        "tier3_finance",
        "tier4_pharma",
        "tier5_enterprise",
        "tier6_backend",
    }
    valid_os_domains = {
        "family",
        "health",
        "finance",
        "pharma",
        "enterprise",
        "bank",
        "gov",
        "agri",
    }

    seen_ids: set[str] = set()
    for q in ALL_QUERIES:
        # Duplicate ID
        if q["id"] in seen_ids:
            issues.append(f"DUPLICATE_ID: {q['id']}")
        seen_ids.add(q["id"])

        # Expected native app exists
        if q["expected_native_app"] not in all_native_app_ids:
            issues.append(f"UNKNOWN_APP: {q['id']} -> {q['expected_native_app']}")

        # Valid tier
        if q["tier"] not in valid_tiers:
            issues.append(f"BAD_TIER: {q['id']} -> {q['tier']}")

        # Active OS set valid
        for domain in q["active_os_set"]:
            if domain not in valid_os_domains:
                issues.append(f"BAD_OS_DOMAIN: {q['id']} -> {domain}")

        # Expected app is in an active OS domain (sanity)
        # We can't check this without OS domain map, but flag obvious errors

        # Backend hints must not match expected_native_app
        for hint in q["backend_hints"]:
            if hint.lower().replace(" ", "") in q["expected_native_app"].lower().replace(".", ""):
                issues.append(f"BACKEND_IS_APP: {q['id']} -> {hint}")

    return issues


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from scripts.poc_v2.native_app_stubs import ALL_STUBS

    ALL_IDS = {
        "family.calendar",
        "family.shopping",
        "family.tasks",
        "family.reminders",
        "family.chores",
        "family.family_settings",
    } | set(ALL_STUBS.keys())

    if "--validate" in sys.argv:
        problems = validate(ALL_IDS)
        if problems:
            for p in problems:
                print(f"  ❌ {p}")
            print(f"\n{len(problems)} issues found.")
            sys.exit(1)
        print(f"  ✅ All {len(ALL_QUERIES)} queries valid.")
        by_tier = get_queries_by_tier()
        for tier, queries in sorted(by_tier.items()):
            print(f"    {tier}: {len(queries)} queries")
    elif "--list" in sys.argv:
        by_tier = get_queries_by_tier()
        for tier, queries in sorted(by_tier.items()):
            print(f"\n{tier} ({len(queries)} queries):")
            for q in queries:
                print(f"  {q['id']}: \"{q['utterance'][:80]}\" → {q['expected_native_app']}")
    else:
        print(f"  {len(ALL_QUERIES)} total queries across 6 tiers.")
        by_tier = get_queries_by_tier()
        for tier, queries in sorted(by_tier.items()):
            print(f"    {tier}: {len(queries)} queries")
