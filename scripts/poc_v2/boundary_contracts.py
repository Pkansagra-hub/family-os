"""
POC v2: Native-App Boundary Contracts — 33 apps
=================================================
Defines what each native app OWNS and DOES NOT OWN.

This is the resolver's "spine" — used for:
  - Schema compatibility scoring (resource_kind match, effect match)
  - Hard veto (query mentions resource this app doesn't own → score 0.0)
  - Cross-app disambiguation (ambiguous_with examples)

Data sources:
  - scripts/intent_schema_generator.py (resource_kinds, confusable_with)
  - k1/docs/future_family_apps_development.md (tool descriptions, backends)
  - Direct knowledge of the 6 real FamilyOS definitions

Usage:
  python scripts/poc_v2/boundary_contracts.py --validate
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NativeAppBoundary:
    """Compact manifest declaring what a native app owns and doesn't own."""

    native_app: str
    os_domain: str
    owns_resources: list[str]  # resource kinds this app MANAGES
    does_not_own_resources: list[str]  # resource kinds this app NEVER touches
    owns_effects: list[str]  # valid effects: read, create, update, delete, complete, execute
    ambiguous_with: dict[str, list[str]]  # {other_app_id: [example_queries_that_are_ambiguous]}
    backend_slots: dict[str, list[str]]  # {slot_type: [example_backend_names]}


# ═══════════════════════════════════════════════════════════════════════════
# FamilyOS (6 apps — real definitions)
# ═══════════════════════════════════════════════════════════════════════════

FAMILY_CALENDAR = NativeAppBoundary(
    native_app="family.calendar",
    os_domain="family",
    owns_resources=[
        "event",
        "appointment",
        "meeting",
        "booking",
        "schedule",
        "rsvp",
        "recurring_event",
    ],
    does_not_own_resources=[
        "prescription",
        "medication",
        "bank_transaction",
        "shopping_item",
        "lab_result",
        "vital",
    ],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "health.appointments": [
            "schedule a doctor appointment",
            "what time is my annual physical",
            "reschedule my dermatology visit",
        ],
        "family.reminders": [
            "remind me about the dentist tomorrow",
            "don't let me forget the parent-teacher conference",
        ],
        "family.tasks": [
            "plan the birthday party for Saturday",
            "organize the family reunion",
        ],
    },
    backend_slots={
        "calendar_providers": ["google-calendar", "outlook", "apple-calendar", "caldav"],
    },
)

FAMILY_SHOPPING = NativeAppBoundary(
    native_app="family.shopping",
    os_domain="family",
    owns_resources=[
        "item",
        "shopping_list",
        "order",
        "price",
        "cart",
        "grocery",
        "household_supply",
    ],
    does_not_own_resources=["calendar_event", "prescription", "bank_transaction", "task", "vital"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "family.tasks": [
            "pick up milk on the way home",
            "get groceries for the party",
        ],
        "family.chores": [
            "we're out of dish soap",
            "restock the cleaning supplies",
        ],
        "finance.budgeting": [
            "how much did we spend on groceries",
            "we're over budget on food this month",
        ],
    },
    backend_slots={
        "grocery_retailers": [
            "walmart",
            "kroger",
            "costco",
            "aldi",
            "target",
            "whole-foods",
            "publix",
        ],
        "delivery_services": ["doordash", "ubereats", "instacart", "grubhub", "amazon-fresh"],
    },
)

FAMILY_TASKS = NativeAppBoundary(
    native_app="family.tasks",
    os_domain="family",
    owns_resources=["task", "todo", "assignment", "errand", "project", "deadline", "homework"],
    does_not_own_resources=[
        "calendar_event",
        "chore",
        "prescription",
        "bank_transaction",
        "shopping_item",
    ],
    owns_effects=["read", "create", "update", "delete", "complete"],
    ambiguous_with={
        "family.chores": [
            "clean the garage this weekend",
            "mow the lawn before Saturday",
        ],
        "family.shopping": [
            "get groceries for the week",
            "pick up the dry cleaning",
        ],
        "family.reminders": [
            "don't forget to submit the permission slip",
            "remind Riley about the book report",
        ],
        "enterprise.project_mgmt": [
            "track my work tasks for the sprint",
            "what tickets do I have this week",
        ],
    },
    backend_slots={
        "task_providers": [
            "todoist",
            "ticktick",
            "microsoft-todo",
            "anydo",
            "trello",
            "asana",
            "clickup",
        ],
    },
)

FAMILY_REMINDERS = NativeAppBoundary(
    native_app="family.reminders",
    os_domain="family",
    owns_resources=["reminder", "alert", "notification", "nudge", "ping", "alarm"],
    does_not_own_resources=[
        "prescription",
        "medication",
        "lab_result",
        "vital",
        "bank_transaction",
    ],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "family.calendar": [
            "remind me about the dentist tomorrow at 10am",
            "alert me an hour before the soccer game",
        ],
        "family.tasks": [
            "don't let me forget to submit the form",
            "remind Riley about the science project deadline",
        ],
        "health.medications": [
            "remind me to take my pills",
            "set a daily reminder for my evening medication",
            "alert me when it's time for my insulin",
        ],
        "health.vitals": [
            "remind me to check my blood pressure",
            "nudge me to log my weight",
        ],
    },
    backend_slots={
        "reminder_apps": ["apple-reminders", "google-keep", "due", "medisafe", "waterminder"],
    },
)

FAMILY_CHORES = NativeAppBoundary(
    native_app="family.chores",
    os_domain="family",
    owns_resources=["chore", "routine", "household_duty", "cleaning_task", "zone", "rotation"],
    does_not_own_resources=["prescription", "bank_transaction", "calendar_event", "shopping_item"],
    owns_effects=["read", "create", "update", "delete", "complete"],
    ambiguous_with={
        "family.tasks": [
            "organize the garage",
            "clean out the fridge",
        ],
        "family.shopping": [
            "we're out of cleaning supplies",
            "restock the laundry detergent",
        ],
        "family.reminders": [
            "remind me to take out the trash tonight",
            "don't forget to feed the dog",
        ],
    },
    backend_slots={
        "chore_apps": ["tody", "sweepy", "ourhome", "chorsee", "nipto", "maple"],
    },
)

FAMILY_SETTINGS = NativeAppBoundary(
    native_app="family.family_settings",
    os_domain="family",
    owns_resources=[
        "setting",
        "preference",
        "feature_flag",
        "policy",
        "toggle",
        "config",
        "permission",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "prescription",
        "bank_transaction",
        "task",
    ],
    owns_effects=["read", "update"],
    ambiguous_with={
        "family.shopping": [
            "turn off shopping approvals for Emma",
        ],
        "family.chores": [
            "change the chore rotation setting",
        ],
    },
    backend_slots={},
)

# ═══════════════════════════════════════════════════════════════════════════
# HealthOS (7 apps)
# ═══════════════════════════════════════════════════════════════════════════

HEALTH_RECORDS = NativeAppBoundary(
    native_app="health.records",
    os_domain="health",
    owns_resources=[
        "health_record",
        "patient_history",
        "lab_result",
        "imaging_report",
        "referral",
        "allergy",
        "immunization",
        "diagnosis",
        "condition",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "bank_transaction",
        "task",
        "chore",
        "prescription_refill",
    ],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "health.lab_results": [
            "show me my blood work",
            "what were my last lab results",
        ],
        "health.medications": [
            "what medications am I on",
            "show me my prescription history",
        ],
        "health.insurance": [
            "does my record show this procedure was covered",
        ],
    },
    backend_slots={
        "ehr_systems": [
            "epic-mychart",
            "cerner",
            "athenahealth",
            "allscripts",
            "apple-health-records",
            "va-health",
        ],
    },
)

HEALTH_APPOINTMENTS = NativeAppBoundary(
    native_app="health.appointments",
    os_domain="health",
    owns_resources=[
        "appointment",
        "provider",
        "availability_slot",
        "telehealth_session",
        "followup",
        "specialist",
    ],
    does_not_own_resources=["shopping_item", "bank_transaction", "chore", "prescription"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "family.calendar": [
            "schedule a doctor visit for Tuesday",
            "what appointments do I have this week",
            "add my physical to my calendar",
        ],
        "health.records": [
            "find the doctor I saw last year",
        ],
        "health.insurance": [
            "find a dermatologist in my network",
        ],
    },
    backend_slots={
        "scheduling_platforms": [
            "zocdoc",
            "epic-telehealth",
            "doxy-me",
            "amwell",
            "teladoc",
            "zoom-healthcare",
        ],
    },
)

HEALTH_MEDICATIONS = NativeAppBoundary(
    native_app="health.medications",
    os_domain="health",
    owns_resources=[
        "prescription",
        "medication",
        "refill",
        "interaction",
        "dose",
        "vaccine",
        "medication_schedule",
    ],
    does_not_own_resources=["shopping_item", "calendar_event", "bank_transaction", "chore", "task"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "family.reminders": [
            "remind me to take my pills",
            "set a medication alarm for 8pm",
            "don't let me forget my evening dose",
        ],
        "pharmaos.fulfillment": [
            "refill my prescription",
            "is my medication ready",
            "pick up my Lipitor",
        ],
        "health.records": [
            "show me my current medications",
            "what prescriptions am I taking",
        ],
        "health.vitals": [
            "track my blood pressure medication effectiveness",
        ],
    },
    backend_slots={
        "pharmacies": [
            "cvs",
            "walgreens",
            "rite-aid",
            "capsule",
            "alto",
            "hospital-pharmacy",
            "mail-order",
        ],
        "drug_databases": ["drugs-com", "fda", "epocrates", "micromedex"],
    },
)

HEALTH_VITALS = NativeAppBoundary(
    native_app="health.vitals",
    os_domain="health",
    owns_resources=[
        "vital",
        "health_metric",
        "sleep_data",
        "activity_data",
        "health_goal",
        "wearable_data",
    ],
    does_not_own_resources=["shopping_item", "bank_transaction", "chore", "prescription", "task"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "health.records": [
            "show me my health data",
            "what's my health history",
        ],
        "health.medications": [
            "is my blood pressure normal on this medication",
        ],
        "family.reminders": [
            "remind me to check my weight",
            "nudge me to log my blood sugar",
        ],
    },
    backend_slots={
        "wearables": [
            "fitbit",
            "apple-health",
            "garmin",
            "oura",
            "whoop",
            "withings",
            "samsung-health",
        ],
        "fitness_apps": ["strava", "myfitnesspal", "peloton", "cronometer"],
    },
)

HEALTH_INSURANCE = NativeAppBoundary(
    native_app="health.insurance",
    os_domain="health",
    owns_resources=[
        "insurance_claim",
        "coverage",
        "deductible",
        "in_network_provider",
        "cost_estimate",
        "prior_authorization",
        "appeal",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "chore",
        "task",
        "auto_insurance",
        "home_insurance",
    ],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "finance.insurance": [
            "is my insurance up for renewal",
            "compare insurance plans",
        ],
        "health.records": [
            "does my insurance cover this procedure",
        ],
        "health.appointments": [
            "find a provider who takes my insurance",
        ],
        "pharmaos.insurance": [
            "how much will this prescription cost",
            "does my plan cover this medication",
        ],
    },
    backend_slots={
        "insurers": [
            "aetna",
            "unitedhealth",
            "blue-cross",
            "cigna",
            "humana",
            "medicare",
            "medicaid",
        ],
    },
)

HEALTH_CAREGIVING = NativeAppBoundary(
    native_app="health.caregiving",
    os_domain="health",
    owns_resources=[
        "care_plan",
        "care_team",
        "adl_log",
        "emergency_contact",
        "shared_record",
        "caregiver_note",
    ],
    does_not_own_resources=[
        "shopping_item",
        "bank_transaction",
        "prescription_refill",
        "calendar_event",
    ],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "health.records": [
            "show me Mom's medical history",
            "what conditions does Dad have",
        ],
        "family.tasks": [
            "check on Mom today",
            "help Dad with his medication",
        ],
        "health.appointments": [
            "schedule a home health aide visit",
        ],
    },
    backend_slots={
        "caregiver_platforms": ["carezone", "lotsa-helping-hands", "caring-bridge", "carely"],
    },
)

HEALTH_LAB_RESULTS = NativeAppBoundary(
    native_app="health.lab_results",
    os_domain="health",
    owns_resources=[
        "lab_result",
        "lab_order",
        "reference_range",
        "trend",
        "lab_appointment",
        "blood_test",
        "diagnostic_test",
    ],
    does_not_own_resources=[
        "shopping_item",
        "bank_transaction",
        "chore",
        "prescription",
        "calendar_event",
    ],
    owns_effects=["read", "create"],
    ambiguous_with={
        "health.records": [
            "show me my test results",
            "what did my blood work show",
        ],
        "health.medications": [
            "check my A1C levels",
            "what were my cholesterol numbers",
        ],
        "health.vitals": [
            "track my lab values over time",
        ],
    },
    backend_slots={
        "lab_providers": [
            "labcorp",
            "quest-diagnostics",
            "bioreference",
            "hospital-labs",
            "home-test-kits",
        ],
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# FinanceOS (6 apps)
# ═══════════════════════════════════════════════════════════════════════════

FINANCE_ACCOUNTS = NativeAppBoundary(
    native_app="finance.accounts",
    os_domain="finance",
    owns_resources=["account", "balance", "transaction", "statement", "transfer", "net_worth"],
    does_not_own_resources=["shopping_item", "calendar_event", "chore", "prescription", "vital"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "finance.budgeting": [
            "how much money do I have left this month",
            "track my spending",
        ],
        "finance.investing": [
            "what's my total portfolio balance",
        ],
    },
    backend_slots={
        "banks": [
            "chase",
            "bofa",
            "wells-fargo",
            "citi",
            "us-bank",
            "capital-one",
            "credit-unions",
        ],
        "payment_apps": ["venmo", "paypal", "cash-app", "apple-cash"],
    },
)

FINANCE_BUDGETING = NativeAppBoundary(
    native_app="finance.budgeting",
    os_domain="finance",
    owns_resources=[
        "budget",
        "expense",
        "category",
        "spending_limit",
        "savings_goal",
        "bill",
        "subscription",
        "cash_flow",
    ],
    does_not_own_resources=["shopping_item", "calendar_event", "prescription", "vital", "chore"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "finance.accounts": [
            "how much did I spend last month",
            "show me my recent transactions",
        ],
        "family.shopping": [
            "how much did we spend on groceries this month",
            "we're over budget on food",
        ],
        "finance.loans": [
            "can I afford a bigger mortgage payment",
        ],
    },
    backend_slots={
        "budgeting_apps": ["mint", "ynab", "everydollar", "copilot", "monarch", "simplifi"],
        "bill_negotiators": ["billshark", "trim", "rocket-money"],
    },
)

FINANCE_INVESTING = NativeAppBoundary(
    native_app="finance.investing",
    os_domain="finance",
    owns_resources=[
        "portfolio",
        "trade",
        "holding",
        "dividend",
        "gain_loss",
        "price_alert",
        "asset_allocation",
        "crypto",
    ],
    does_not_own_resources=["shopping_item", "calendar_event", "prescription", "chore", "vital"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "finance.accounts": [
            "what's my total balance across everything",
            "show me all my money",
        ],
    },
    backend_slots={
        "brokerages": [
            "robinhood",
            "fidelity",
            "vanguard",
            "schwab",
            "etrade",
            "webull",
            "m1-finance",
            "betterment",
            "wealthfront",
        ],
        "crypto_exchanges": ["coinbase", "binance", "kraken", "gemini", "metamask"],
    },
)

FINANCE_TAXES = NativeAppBoundary(
    native_app="finance.taxes",
    os_domain="finance",
    owns_resources=[
        "tax_document",
        "filing",
        "deduction",
        "w2",
        "1099",
        "tax_return",
        "tax_refund",
        "withholding",
    ],
    does_not_own_resources=["shopping_item", "calendar_event", "chore", "prescription", "vital"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "finance.accounts": [
            "download my tax documents",
            "show me my income for the year",
        ],
        "enterprise.payroll": [
            "check my W-2 withholding",
        ],
    },
    backend_slots={
        "tax_software": ["turbotax", "hr-block", "taxact", "freetaxusa"],
        "tax_authorities": ["irs", "state-revenue-department"],
    },
)

FINANCE_INSURANCE = NativeAppBoundary(
    native_app="finance.insurance",
    os_domain="finance",
    owns_resources=[
        "insurance_policy",
        "premium",
        "claim",
        "coverage",
        "beneficiary",
        "auto_insurance",
        "home_insurance",
        "life_insurance",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "chore",
        "prescription",
        "vital",
        "health_insurance",
    ],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "health.insurance": [
            "is my insurance up for renewal",
            "file an insurance claim",
            "what does my insurance cover",
        ],
        "finance.accounts": [
            "how much am I paying for insurance each month",
        ],
    },
    backend_slots={
        "insurers": [
            "geico",
            "progressive",
            "state-farm",
            "allstate",
            "lemonade",
            "hippo",
            "metlife",
        ],
        "comparison_sites": ["policygenius", "zebra", "insurify"],
    },
)

FINANCE_LOANS = NativeAppBoundary(
    native_app="finance.loans",
    os_domain="finance",
    owns_resources=[
        "loan",
        "mortgage",
        "payment_schedule",
        "payoff_balance",
        "refinance",
        "auto_loan",
        "student_loan",
        "personal_loan",
    ],
    does_not_own_resources=["shopping_item", "calendar_event", "prescription", "chore", "vital"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "finance.accounts": [
            "what's my mortgage balance",
            "how much debt do I have",
        ],
        "finance.budgeting": [
            "can I afford this car payment",
        ],
    },
    backend_slots={
        "loan_servicers": ["nelnet", "fedloan", "aidvantage", "sofi", "lendingclub"],
        "refinance_marketplaces": ["lendingtree", "credible"],
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# PharmaOS (6 apps)
# ═══════════════════════════════════════════════════════════════════════════

PHARMAOS_FULFILLMENT = NativeAppBoundary(
    native_app="pharmaos.fulfillment",
    os_domain="pharma",
    owns_resources=[
        "prescription_order",
        "fill_queue",
        "dispensing",
        "pickup",
        "delivery",
        "pharmacist_review",
        "e_prescription",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "bank_transaction",
        "task",
        "vital",
        "health_record",
    ],
    owns_effects=["read", "create", "update", "complete"],
    ambiguous_with={
        "health.medications": [
            "refill my prescription",
            "is my medication ready",
            "renew my Lipitor",
        ],
        "family.reminders": [
            "remind me to pick up my prescription",
        ],
        "pharmaos.insurance": [
            "how much will this cost with my insurance",
        ],
    },
    backend_slots={
        "pharmacy_chains": ["cvs", "walgreens", "rite-aid", "capsule", "alto"],
        "prescription_networks": ["surescripts", "epcs"],
        "automation": ["scriptpro", "parata", "omnicell"],
    },
)

PHARMAOS_INVENTORY = NativeAppBoundary(
    native_app="pharmaos.inventory",
    os_domain="pharma",
    owns_resources=[
        "inventory",
        "stock_level",
        "reorder",
        "cold_chain",
        "lot_number",
        "controlled_substance",
        "expiration",
        "drug_recall",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "prescription_refill",
        "task",
        "vital",
    ],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "pharmaos.fulfillment": [
            "do we have this medication in stock",
            "check the amoxicillin supply",
        ],
        "pharmaos.compliance": [
            "track controlled substance inventory",
        ],
    },
    backend_slots={
        "wholesalers": ["mckesson", "cardinal", "amerisourcebergen"],
        "manufacturers": ["pfizer", "novartis", "johnson-and-johnson"],
    },
)

PHARMAOS_INSURANCE = NativeAppBoundary(
    native_app="pharmaos.insurance",
    os_domain="pharma",
    owns_resources=[
        "claim_adjudication",
        "prior_authorization",
        "copay",
        "formulary",
        "manufacturer_coupon",
        "medicare_part_d",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "bank_transaction",
        "chore",
        "health_record",
    ],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "health.insurance": [
            "does my insurance cover this medication",
            "how much will this cost with insurance",
        ],
        "pharmaos.fulfillment": [
            "process the insurance for this prescription",
        ],
    },
    backend_slots={
        "pbms": ["express-scripts", "cvs-caremark", "optumrx"],
        "discount_programs": ["goodrx", "singlecare", "rxsave"],
    },
)

PHARMAOS_CUSTOMER = NativeAppBoundary(
    native_app="pharmaos.customer",
    os_domain="pharma",
    owns_resources=[
        "patient_notification",
        "pickup_reminder",
        "refill_reminder",
        "counseling_note",
        "satisfaction_survey",
        "pharmacy_hours",
    ],
    does_not_own_resources=["shopping_item", "bank_transaction", "vital", "prescription_order"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "family.reminders": [
            "text me when my prescription is ready",
            "remind me to pick up my medication",
        ],
        "pharmaos.fulfillment": [
            "notify the patient their order is ready",
        ],
        "health.caregiving": [
            "check on the patient's pickup history",
        ],
    },
    backend_slots={
        "communication_channels": ["sms", "push-notification", "email", "ivr"],
    },
)

PHARMAOS_COMPLIANCE = NativeAppBoundary(
    native_app="pharmaos.compliance",
    os_domain="pharma",
    owns_resources=[
        "dea_log",
        "hipaa_audit",
        "board_compliance",
        "usp_797",
        "usp_800",
        "medication_error",
        "root_cause_analysis",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "bank_transaction",
        "vital",
        "prescription_refill",
    ],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "pharmaos.inventory": [
            "log this controlled substance dispensing",
        ],
    },
    backend_slots={
        "regulatory_systems": ["dea-csos", "arcos", "state-bop", "ismp"],
    },
)

PHARMAOS_COMPOUNDING = NativeAppBoundary(
    native_app="pharmaos.compounding",
    os_domain="pharma",
    owns_resources=[
        "compounding_formula",
        "batch",
        "beyond_use_date",
        "potency_test",
        "sterility_test",
        "compliance_packaging",
    ],
    does_not_own_resources=[
        "shopping_item",
        "calendar_event",
        "bank_transaction",
        "vital",
        "health_record",
    ],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "pharmaos.fulfillment": [
            "prepare this specialty medication",
        ],
        "pharmaos.inventory": [
            "track this compound batch",
        ],
    },
    backend_slots={
        "testing_labs": ["eagle-analytical", "arl-bio-pharma", "element"],
        "packaging_suppliers": ["mckesson-packaging", "drug-package"],
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# EnterpriseOS (8 apps)
# ═══════════════════════════════════════════════════════════════════════════

ENTERPRISE_HR = NativeAppBoundary(
    native_app="enterprise.hr",
    os_domain="enterprise",
    owns_resources=[
        "employee",
        "leave_request",
        "review",
        "onboarding_task",
        "policy_document",
        "pto",
        "benefits_enrollment",
    ],
    does_not_own_resources=["shopping_item", "prescription", "vital", "chore", "calendar_event"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "enterprise.payroll": [
            "view my pay stub",
            "update my tax withholding",
        ],
        "family.calendar": [
            "request time off next week",
            "I'm out of office Friday",
        ],
        "enterprise.crm": [
            "find the new hire's contact info",
        ],
    },
    backend_slots={
        "hr_platforms": ["workday", "bamboohr", "gusto", "adp", "rippling", "sap-successfactors"],
        "performance_tools": ["lattice", "15five", "culture-amp"],
        "recruiting_tools": ["greenhouse", "lever", "linkedin-recruiter"],
    },
)

ENTERPRISE_PAYROLL = NativeAppBoundary(
    native_app="enterprise.payroll",
    os_domain="enterprise",
    owns_resources=[
        "payroll_run",
        "salary",
        "tax_withholding",
        "payslip",
        "direct_deposit",
        "garnishment",
        "bonus",
    ],
    does_not_own_resources=["shopping_item", "prescription", "vital", "chore", "calendar_event"],
    owns_effects=["read", "create", "update"],
    ambiguous_with={
        "enterprise.hr": [
            "view my compensation details",
            "update my benefits",
        ],
        "finance.taxes": [
            "check my W-2",
            "update withholding allowances",
        ],
    },
    backend_slots={
        "payroll_providers": ["adp", "gusto", "rippling", "paychex", "quickbooks-payroll"],
    },
)

ENTERPRISE_PROJECT_MGMT = NativeAppBoundary(
    native_app="enterprise.project_mgmt",
    os_domain="enterprise",
    owns_resources=[
        "project",
        "ticket",
        "sprint",
        "milestone",
        "epic",
        "backlog_item",
        "bug",
        "story",
        "task",
    ],
    does_not_own_resources=[
        "shopping_item",
        "prescription",
        "vital",
        "chore",
        "calendar_event",
        "bank_transaction",
    ],
    owns_effects=["read", "create", "update", "delete", "complete"],
    ambiguous_with={
        "family.tasks": [
            "what do I need to work on today",
            "create a task for the login fix",
            "assign this to me",
        ],
        "enterprise.devops": [
            "file a bug for the deployment issue",
            "track this incident resolution",
        ],
        "enterprise.documentation": [
            "create a page for the new project",
        ],
    },
    backend_slots={
        "project_tools": ["jira", "linear", "asana", "monday-com", "clickup", "trello"],
    },
)

ENTERPRISE_CRM = NativeAppBoundary(
    native_app="enterprise.crm",
    os_domain="enterprise",
    owns_resources=[
        "contact",
        "lead",
        "deal",
        "opportunity",
        "account",
        "pipeline",
        "customer_health",
        "renewal",
        "churn",
    ],
    does_not_own_resources=["shopping_item", "prescription", "vital", "chore", "calendar_event"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "enterprise.communication": [
            "find the client's email thread",
            "message the Acme Corp team",
        ],
        "enterprise.project_mgmt": [
            "track this deal through to close",
        ],
    },
    backend_slots={
        "crm_platforms": [
            "salesforce",
            "hubspot",
            "zoho",
            "pipedrive",
            "freshsales",
            "intercom",
            "zendesk",
        ],
    },
)

ENTERPRISE_DOCUMENTATION = NativeAppBoundary(
    native_app="enterprise.documentation",
    os_domain="enterprise",
    owns_resources=[
        "document",
        "wiki_page",
        "knowledge_article",
        "folder",
        "template",
        "sop",
        "runbook",
        "playbook",
    ],
    does_not_own_resources=["shopping_item", "prescription", "vital", "chore", "bank_transaction"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "enterprise.project_mgmt": [
            "create a document for the new feature spec",
        ],
        "enterprise.communication": [
            "share the onboarding guide with the team",
        ],
    },
    backend_slots={
        "doc_platforms": [
            "confluence",
            "notion",
            "sharepoint",
            "google-drive",
            "dropbox-paper",
            "gitbook",
        ],
    },
)

ENTERPRISE_COMMUNICATION = NativeAppBoundary(
    native_app="enterprise.communication",
    os_domain="enterprise",
    owns_resources=[
        "message",
        "channel",
        "thread",
        "email",
        "meeting",
        "call",
        "presence",
        "inbox",
    ],
    does_not_own_resources=["shopping_item", "prescription", "vital", "chore", "bank_transaction"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "enterprise.crm": [
            "search for the client conversation",
        ],
        "enterprise.documentation": [
            "send the document to the team",
        ],
        "family.calendar": [
            "schedule a meeting for 3pm",
        ],
    },
    backend_slots={
        "messaging_platforms": [
            "slack",
            "microsoft-teams",
            "discord",
            "whatsapp-business",
            "telegram",
        ],
        "meeting_platforms": ["zoom", "google-meet", "microsoft-teams", "webex"],
        "email_platforms": ["gmail", "outlook"],
    },
)

ENTERPRISE_DEVOPS = NativeAppBoundary(
    native_app="enterprise.devops",
    os_domain="enterprise",
    owns_resources=[
        "deployment",
        "incident",
        "alert",
        "pipeline",
        "build",
        "release",
        "infrastructure",
        "on_call",
        "runbook",
        "rollback",
    ],
    does_not_own_resources=[
        "shopping_item",
        "prescription",
        "vital",
        "chore",
        "calendar_event",
        "hr_document",
    ],
    owns_effects=["read", "create", "update", "execute"],
    ambiguous_with={
        "enterprise.project_mgmt": [
            "track the deployment bug",
            "create a ticket for the incident",
        ],
        "enterprise.it": [
            "the service is down",
            "investigate the production issue",
        ],
    },
    backend_slots={
        "monitoring": ["pagerduty", "opsgenie", "datadog", "sentry", "grafana", "cloudwatch"],
        "ci_cd": ["github-actions", "gitlab-ci", "circleci", "jenkins", "argocd", "spinnaker"],
        "clouds": ["aws", "gcp", "azure", "kubernetes"],
    },
)

ENTERPRISE_IT = NativeAppBoundary(
    native_app="enterprise.it",
    os_domain="enterprise",
    owns_resources=[
        "it_ticket",
        "asset",
        "access_review",
        "security_alert",
        "change_request",
        "vpn",
        "laptop",
        "software_license",
    ],
    does_not_own_resources=["shopping_item", "prescription", "vital", "chore", "bank_transaction"],
    owns_effects=["read", "create", "update", "delete"],
    ambiguous_with={
        "enterprise.devops": [
            "the production server is down",
            "investigate the security alert",
        ],
        "enterprise.communication": [
            "my email isn't working",
        ],
    },
    backend_slots={
        "itsm_platforms": [
            "servicenow",
            "jira-service-management",
            "zendesk",
            "freshservice",
            "ivanti",
        ],
        "identity_providers": ["okta", "azure-ad", "jumpcloud", "duo", "sailpoint"],
        "security_tools": ["crowdstrike", "sentinelone", "splunk", "palo-alto", "wiz"],
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# Master registry
# ═══════════════════════════════════════════════════════════════════════════

ALL_BOUNDARIES: dict[str, NativeAppBoundary] = {
    # FamilyOS
    "family.calendar": FAMILY_CALENDAR,
    "family.shopping": FAMILY_SHOPPING,
    "family.tasks": FAMILY_TASKS,
    "family.reminders": FAMILY_REMINDERS,
    "family.chores": FAMILY_CHORES,
    "family.family_settings": FAMILY_SETTINGS,
    # HealthOS
    "health.records": HEALTH_RECORDS,
    "health.appointments": HEALTH_APPOINTMENTS,
    "health.medications": HEALTH_MEDICATIONS,
    "health.vitals": HEALTH_VITALS,
    "health.insurance": HEALTH_INSURANCE,
    "health.caregiving": HEALTH_CAREGIVING,
    "health.lab_results": HEALTH_LAB_RESULTS,
    # FinanceOS
    "finance.accounts": FINANCE_ACCOUNTS,
    "finance.budgeting": FINANCE_BUDGETING,
    "finance.investing": FINANCE_INVESTING,
    "finance.taxes": FINANCE_TAXES,
    "finance.insurance": FINANCE_INSURANCE,
    "finance.loans": FINANCE_LOANS,
    # PharmaOS
    "pharmaos.fulfillment": PHARMAOS_FULFILLMENT,
    "pharmaos.inventory": PHARMAOS_INVENTORY,
    "pharmaos.insurance": PHARMAOS_INSURANCE,
    "pharmaos.customer": PHARMAOS_CUSTOMER,
    "pharmaos.compliance": PHARMAOS_COMPLIANCE,
    "pharmaos.compounding": PHARMAOS_COMPOUNDING,
    # EnterpriseOS
    "enterprise.hr": ENTERPRISE_HR,
    "enterprise.payroll": ENTERPRISE_PAYROLL,
    "enterprise.project_mgmt": ENTERPRISE_PROJECT_MGMT,
    "enterprise.crm": ENTERPRISE_CRM,
    "enterprise.documentation": ENTERPRISE_DOCUMENTATION,
    "enterprise.communication": ENTERPRISE_COMMUNICATION,
    "enterprise.devops": ENTERPRISE_DEVOPS,
    "enterprise.it": ENTERPRISE_IT,
}


def validate() -> list[str]:
    """Validate all boundary contracts. Returns list of issues (empty = clean)."""
    issues: list[str] = []
    valid_effects = {"read", "create", "update", "delete", "complete", "execute"}

    for boundary in ALL_BOUNDARIES.values():
        # Must have at least 3 owns_resources
        if len(boundary.owns_resources) < 3:
            issues.append(f"FEW_OWNS: {boundary.native_app} ({len(boundary.owns_resources)})")

        # Must have at least 1 does_not_own_resources
        if len(boundary.does_not_own_resources) < 1:
            issues.append(f"NO_DOES_NOT_OWN: {boundary.native_app}")

        # owns_resources and does_not_own_resources must not overlap
        overlap = set(boundary.owns_resources) & set(boundary.does_not_own_resources)
        if overlap:
            issues.append(f"OWN_CONFLICT: {boundary.native_app} -> {overlap}")

        # owns_effects must be valid
        for effect in boundary.owns_effects:
            if effect not in valid_effects:
                issues.append(f"BAD_EFFECT: {boundary.native_app} -> {effect}")

        # ambiguous_with must reference real apps
        for ref in boundary.ambiguous_with:
            if ref not in ALL_BOUNDARIES:
                issues.append(f"UNKNOWN_AMBIGUOUS: {boundary.native_app} -> {ref}")

        # ambiguous_with must have at least 1 example per entry
        for ref, examples in boundary.ambiguous_with.items():
            if len(examples) < 1:
                issues.append(f"EMPTY_EXAMPLES: {boundary.native_app} -> {ref}")

    return issues


if __name__ == "__main__":
    import sys

    if "--validate" in sys.argv:
        problems = validate()
        if problems:
            for p in problems:
                print(f"  ❌ {p}")
            print(f"\n{len(problems)} issues found.")
            sys.exit(1)
        print(f"  ✅ All {len(ALL_BOUNDARIES)} boundary contracts valid.")
    elif "--list" in sys.argv:
        for b in ALL_BOUNDARIES.values():
            print(f"  {b.native_app} ({b.os_domain})")
            print(f"    owns: {', '.join(b.owns_resources[:8])}")
            print(f"    NOT:  {', '.join(b.does_not_own_resources[:5])}")
            print(f"    ambiguous_with: {', '.join(b.ambiguous_with.keys())}")
    else:
        print(f"  {len(ALL_BOUNDARIES)} boundary contracts loaded.")
