"""
Universal Intent Schema Training Data Generator — Vertex AI
=============================================================
Generates (query -> schema_fields) pairs covering ALL connector verticals:
FamilyOS, Jira, Salesforce, Tesla, Chase, government portals, smart home, etc.

The classifier predicts universal intent fields:
  effect: create | read | update | delete | complete | execute
  resource_kind: open — any noun the connector operates on
  domain_tag: open — the connector's vertical/domain

Usage:
  $env:GOOGLE_CLOUD_PROJECT="project-33d51855-d616-4fcd-a69"
  $env:GOOGLE_CLOUD_LOCATION="global"
  python scripts/intent_schema_generator.py --count 4000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai
from google.genai import types as genai_types

# ═══════════════════════════════════════════════════════════════════════════
# Effect taxonomy — universal, never changes
# ═══════════════════════════════════════════════════════════════════════════

EFFECTS = ["create", "read", "update", "delete", "complete", "execute"]

# ═══════════════════════════════════════════════════════════════════════════
# Native App Verticals — 51 native apps across 8 OS domains
#
# Native-App-as-Aggregator architecture: external services (Walmart, Costco,
# Epic, Cerner, etc.) are DATA BACKENDS, not peer connectors visible to the
# Back LLM.  The classifier only needs to route to the correct NATIVE APP
# within the user's active OS domain.
#
# Total: 51 native apps, each with distinct resource vocabulary.
# No competing same-domain connectors — one app per activity per domain.
# See: k1/docs/future_family_apps_development.md
# ═══════════════════════════════════════════════════════════════════════════

DOMAIN_VERTICALS = [
    # ══════════════════════════════════════════════════════════════════════
    # FamilyOS (6 native apps) — Household Operating System
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "family.shopping",
        "os_domain": "family",
        "apps": "FamilyOS Shopping — household grocery & goods aggregator",
        "resource_kinds": ["item", "shopping_list", "order", "price", "cart", "grocery"],
        "domain_tags": ["family", "shopping", "household"],
        "confusable_with": "family.tasks family.chores",
    },
    {
        "name": "family.tasks",
        "os_domain": "family",
        "apps": "FamilyOS Tasks — household task & to-do management",
        "resource_kinds": ["task", "todo", "assignment", "errand", "project", "deadline"],
        "domain_tags": ["family", "tasks", "productivity"],
        "confusable_with": "family.chores family.reminders family.shopping",
    },
    {
        "name": "family.calendar",
        "os_domain": "family",
        "apps": "FamilyOS Calendar — family schedule & event management",
        "resource_kinds": ["event", "appointment", "meeting", "booking", "schedule"],
        "domain_tags": ["family", "calendar", "scheduling"],
        "confusable_with": "family.reminders family.tasks",
    },
    {
        "name": "family.chores",
        "os_domain": "family",
        "apps": "FamilyOS Chores — household chore tracking & assignment",
        "resource_kinds": ["chore", "routine", "household_duty", "cleaning_task", "zone"],
        "domain_tags": ["family", "chores", "household"],
        "confusable_with": "family.tasks family.reminders",
    },
    {
        "name": "family.reminders",
        "os_domain": "family",
        "apps": "FamilyOS Reminders — alerts, nudges & notifications",
        "resource_kinds": ["reminder", "alert", "notification", "nudge", "ping"],
        "domain_tags": ["family", "reminders", "alerts"],
        "confusable_with": "family.calendar family.tasks",
    },
    {
        "name": "family.family_settings",
        "os_domain": "family",
        "apps": "FamilyOS Settings — family preferences, feature flags & policies",
        "resource_kinds": ["setting", "preference", "feature_flag", "policy", "toggle", "config"],
        "domain_tags": ["family", "settings", "configuration"],
        "confusable_with": "family.shopping family.tasks",
    },
    # ══════════════════════════════════════════════════════════════════════
    # HealthOS (7 native apps) — Healthcare Operating System
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "health.records",
        "os_domain": "health",
        "apps": "HealthOS Records — unified health records across providers",
        "resource_kinds": [
            "health_record",
            "patient_history",
            "lab_result",
            "imaging_report",
            "referral",
            "allergy",
        ],
        "domain_tags": ["health", "medical", "records"],
        "confusable_with": "health.lab_results health.insurance",
    },
    {
        "name": "health.appointments",
        "os_domain": "health",
        "apps": "HealthOS Appointments — provider search & booking",
        "resource_kinds": [
            "appointment",
            "provider",
            "availability_slot",
            "telehealth_session",
            "followup",
        ],
        "domain_tags": ["health", "appointments", "scheduling"],
        "confusable_with": "family.calendar health.records",
    },
    {
        "name": "health.medications",
        "os_domain": "health",
        "apps": "HealthOS Medications — prescription management & reminders",
        "resource_kinds": [
            "prescription",
            "medication",
            "refill",
            "interaction",
            "dose",
            "vaccine",
        ],
        "domain_tags": ["health", "medications", "pharmacy"],
        "confusable_with": "health.reminders pharma.prescriptions",
    },
    {
        "name": "health.vitals",
        "os_domain": "health",
        "apps": "HealthOS Vitals — wearable & wellness data aggregation",
        "resource_kinds": ["vital", "health_metric", "sleep_data", "activity_data", "health_goal"],
        "domain_tags": ["health", "vitals", "wellness", "fitness"],
        "confusable_with": "health.records family.reminders",
    },
    {
        "name": "health.insurance",
        "os_domain": "health",
        "apps": "HealthOS Insurance — coverage, claims & cost estimation",
        "resource_kinds": [
            "insurance_claim",
            "coverage",
            "deductible",
            "in_network_provider",
            "cost_estimate",
        ],
        "domain_tags": ["health", "insurance", "billing"],
        "confusable_with": "finance.insurance health.records",
    },
    {
        "name": "health.caregiving",
        "os_domain": "health",
        "apps": "HealthOS Caregiving — care plan coordination",
        "resource_kinds": [
            "care_plan",
            "care_team",
            "adl_log",
            "emergency_contact",
            "shared_record",
        ],
        "domain_tags": ["health", "caregiving", "family"],
        "confusable_with": "health.records family.tasks",
    },
    {
        "name": "health.lab_results",
        "os_domain": "health",
        "apps": "HealthOS Lab Results — lab result aggregation & trending",
        "resource_kinds": [
            "lab_result",
            "lab_order",
            "reference_range",
            "trend",
            "lab_appointment",
        ],
        "domain_tags": ["health", "labs", "diagnostics"],
        "confusable_with": "health.records health.medications",
    },
    # ══════════════════════════════════════════════════════════════════════
    # FinanceOS (6 native apps) — Personal Finance Operating System
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "finance.accounts",
        "os_domain": "finance",
        "apps": "FinanceOS Accounts — unified financial account view",
        "resource_kinds": ["account", "balance", "transaction", "statement", "transfer"],
        "domain_tags": ["finance", "banking", "accounts"],
        "confusable_with": "bank.accounts finance.investing",
    },
    {
        "name": "finance.budgeting",
        "os_domain": "finance",
        "apps": "FinanceOS Budgeting — budget tracking & planning",
        "resource_kinds": ["budget", "expense", "category", "spending_limit", "savings_goal"],
        "domain_tags": ["finance", "budgeting", "planning"],
        "confusable_with": "finance.accounts family.shopping",
    },
    {
        "name": "finance.investing",
        "os_domain": "finance",
        "apps": "FinanceOS Investing — portfolio & investment management",
        "resource_kinds": ["portfolio", "trade", "holding", "dividend", "gain_loss", "price_alert"],
        "domain_tags": ["finance", "investing", "wealth"],
        "confusable_with": "finance.accounts bank.accounts",
    },
    {
        "name": "finance.taxes",
        "os_domain": "finance",
        "apps": "FinanceOS Taxes — tax document aggregation & filing",
        "resource_kinds": ["tax_document", "filing", "deduction", "w2", "1099", "tax_return"],
        "domain_tags": ["finance", "taxes", "compliance"],
        "confusable_with": "gov.taxes finance.accounts",
    },
    {
        "name": "finance.insurance",
        "os_domain": "finance",
        "apps": "FinanceOS Insurance — personal insurance policies",
        "resource_kinds": ["insurance_policy", "premium", "claim", "coverage", "beneficiary"],
        "domain_tags": ["finance", "insurance", "protection"],
        "confusable_with": "health.insurance finance.accounts",
    },
    {
        "name": "finance.loans",
        "os_domain": "finance",
        "apps": "FinanceOS Loans — mortgage, auto & personal loan management",
        "resource_kinds": ["loan", "mortgage", "payment_schedule", "payoff_balance", "refinance"],
        "domain_tags": ["finance", "loans", "debt"],
        "confusable_with": "bank.lending finance.accounts",
    },
    # ══════════════════════════════════════════════════════════════════════
    # BankOS (6 native apps) — Banking Infrastructure OS
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "bank.accounts",
        "os_domain": "bank",
        "apps": "BankOS Accounts — checking, savings & CD management",
        "resource_kinds": ["checking_account", "savings_account", "cd", "overdraft", "statement"],
        "domain_tags": ["banking", "accounts", "deposits"],
        "confusable_with": "finance.accounts bank.payments",
    },
    {
        "name": "bank.payments",
        "os_domain": "bank",
        "apps": "BankOS Payments — payments, transfers & wire processing",
        "resource_kinds": ["payment", "wire", "ach", "bill_pay", "zelle", "transfer"],
        "domain_tags": ["banking", "payments", "transfers"],
        "confusable_with": "finance.accounts bank.accounts",
    },
    {
        "name": "bank.lending",
        "os_domain": "bank",
        "apps": "BankOS Lending — loan origination & servicing",
        "resource_kinds": [
            "loan_application",
            "credit_score",
            "underwriting",
            "collateral",
            "amortization",
        ],
        "domain_tags": ["banking", "lending", "credit"],
        "confusable_with": "finance.loans bank.accounts",
    },
    {
        "name": "bank.compliance",
        "os_domain": "bank",
        "apps": "BankOS Compliance — KYC, AML & regulatory reporting",
        "resource_kinds": [
            "kyc_check",
            "aml_alert",
            "regulatory_filing",
            "audit_log",
            "risk_report",
        ],
        "domain_tags": ["banking", "compliance", "regulation"],
        "confusable_with": "gov.records bank.accounts",
    },
    {
        "name": "bank.fraud",
        "os_domain": "bank",
        "apps": "BankOS Fraud — fraud detection & dispute management",
        "resource_kinds": [
            "fraud_alert",
            "dispute",
            "chargeback",
            "transaction_review",
            "blocked_payment",
        ],
        "domain_tags": ["banking", "fraud", "security"],
        "confusable_with": "bank.compliance bank.payments",
    },
    {
        "name": "bank.customer",
        "os_domain": "bank",
        "apps": "BankOS Customer — customer service & onboarding",
        "resource_kinds": [
            "customer_profile",
            "support_ticket",
            "onboarding_case",
            "account_closure",
            "beneficiary",
        ],
        "domain_tags": ["banking", "customer", "service"],
        "confusable_with": "enterprise.crm bank.accounts",
    },
    # ══════════════════════════════════════════════════════════════════════
    # EnterpriseOS (8 native apps) — Business Operations OS
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "enterprise.hr",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS HR — employee records & people operations",
        "resource_kinds": [
            "employee",
            "leave_request",
            "review",
            "onboarding_task",
            "policy_document",
        ],
        "domain_tags": ["enterprise", "hr", "people_ops"],
        "confusable_with": "enterprise.payroll enterprise.crm",
    },
    {
        "name": "enterprise.payroll",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS Payroll — salary, benefits & compensation",
        "resource_kinds": [
            "payroll_run",
            "salary",
            "benefit_enrollment",
            "tax_withholding",
            "payslip",
        ],
        "domain_tags": ["enterprise", "payroll", "compensation"],
        "confusable_with": "enterprise.hr finance.taxes",
    },
    {
        "name": "enterprise.project_mgmt",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS Project Management — projects, tickets & sprints",
        "resource_kinds": ["project", "ticket", "sprint", "milestone", "epic", "backlog_item"],
        "domain_tags": ["enterprise", "project_management", "agile"],
        "confusable_with": "family.tasks enterprise.devops",
    },
    {
        "name": "enterprise.crm",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS CRM — customer & sales relationship management",
        "resource_kinds": ["contact", "lead", "deal", "opportunity", "account", "pipeline"],
        "domain_tags": ["enterprise", "crm", "sales"],
        "confusable_with": "enterprise.communication enterprise.project_mgmt",
    },
    {
        "name": "enterprise.documentation",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS Documentation — docs, wikis & knowledge bases",
        "resource_kinds": ["document", "wiki_page", "knowledge_article", "folder", "template"],
        "domain_tags": ["enterprise", "documentation", "knowledge"],
        "confusable_with": "enterprise.project_mgmt enterprise.communication",
    },
    {
        "name": "enterprise.communication",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS Communication — messaging, email & video",
        "resource_kinds": ["message", "channel", "thread", "email", "meeting", "call"],
        "domain_tags": ["enterprise", "communication", "messaging"],
        "confusable_with": "enterprise.crm enterprise.documentation",
    },
    {
        "name": "enterprise.devops",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS DevOps — CI/CD, monitoring & infrastructure",
        "resource_kinds": [
            "pipeline",
            "deployment",
            "incident",
            "repository",
            "alert",
            "workflow_run",
        ],
        "domain_tags": ["enterprise", "devops", "engineering"],
        "confusable_with": "enterprise.project_mgmt enterprise.security",
    },
    {
        "name": "enterprise.security",
        "os_domain": "enterprise",
        "apps": "EnterpriseOS Security — access control, audits & threat detection",
        "resource_kinds": [
            "access_request",
            "audit_log",
            "security_alert",
            "vulnerability",
            "policy_violation",
        ],
        "domain_tags": ["enterprise", "security", "compliance"],
        "confusable_with": "enterprise.devops bank.compliance",
    },
    # ══════════════════════════════════════════════════════════════════════
    # GovOS (6 native apps) — Government Services OS
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "gov.benefits",
        "os_domain": "gov",
        "apps": "GovOS Benefits — social benefits applications & management",
        "resource_kinds": [
            "benefit_application",
            "eligibility_check",
            "benefit_renewal",
            "payment_history",
            "case_status",
        ],
        "domain_tags": ["government", "benefits", "social_services"],
        "confusable_with": "gov.records health.insurance",
    },
    {
        "name": "gov.permits",
        "os_domain": "gov",
        "apps": "GovOS Permits — licenses, permits & certifications",
        "resource_kinds": [
            "permit_application",
            "license",
            "registration",
            "inspection",
            "certification",
        ],
        "domain_tags": ["government", "permits", "licensing"],
        "confusable_with": "gov.records enterprise.security",
    },
    {
        "name": "gov.records",
        "os_domain": "gov",
        "apps": "GovOS Records — vital records & official documents",
        "resource_kinds": [
            "birth_certificate",
            "marriage_license",
            "court_record",
            "property_deed",
            "official_filing",
        ],
        "domain_tags": ["government", "records", "vital_records"],
        "confusable_with": "gov.permits gov.taxes",
    },
    {
        "name": "gov.taxes",
        "os_domain": "gov",
        "apps": "GovOS Taxes — tax filing & payment to government",
        "resource_kinds": [
            "tax_return",
            "tax_payment",
            "extension_request",
            "audit_notice",
            "assessment",
        ],
        "domain_tags": ["government", "taxes", "revenue"],
        "confusable_with": "finance.taxes gov.records",
    },
    {
        "name": "gov.voting",
        "os_domain": "gov",
        "apps": "GovOS Voting — voter registration & election management",
        "resource_kinds": [
            "voter_registration",
            "ballot",
            "polling_location",
            "election_result",
            "absentee_request",
        ],
        "domain_tags": ["government", "voting", "elections"],
        "confusable_with": "gov.records gov.services",
    },
    {
        "name": "gov.services",
        "os_domain": "gov",
        "apps": "GovOS Services — general government service requests",
        "resource_kinds": [
            "service_request",
            "appointment",
            "complaint",
            "information_request",
            "form_submission",
        ],
        "domain_tags": ["government", "services", "civic"],
        "confusable_with": "gov.benefits gov.permits",
    },
    # ══════════════════════════════════════════════════════════════════════
    # AgriOS (6 native apps) — Agricultural Operations OS
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "agri.crops",
        "os_domain": "agri",
        "apps": "AgriOS Crops — crop planning, monitoring & yield management",
        "resource_kinds": [
            "crop_plan",
            "planting_schedule",
            "yield_record",
            "soil_test",
            "irrigation_log",
            "harvest_order",
        ],
        "domain_tags": ["agriculture", "crops", "farming"],
        "confusable_with": "agri.weather agri.supply_chain",
    },
    {
        "name": "agri.livestock",
        "os_domain": "agri",
        "apps": "AgriOS Livestock — animal health, breeding & feed management",
        "resource_kinds": [
            "animal_record",
            "health_check",
            "breeding_log",
            "feed_order",
            "weight_log",
            "vaccination",
        ],
        "domain_tags": ["agriculture", "livestock", "animal_health"],
        "confusable_with": "agri.crops health.records",
    },
    {
        "name": "agri.equipment",
        "os_domain": "agri",
        "apps": "AgriOS Equipment — machinery tracking & maintenance",
        "resource_kinds": [
            "equipment_log",
            "maintenance_schedule",
            "fuel_usage",
            "gps_track",
            "repair_order",
        ],
        "domain_tags": ["agriculture", "equipment", "maintenance"],
        "confusable_with": "agri.supply_chain enterprise.devops",
    },
    {
        "name": "agri.supply_chain",
        "os_domain": "agri",
        "apps": "AgriOS Supply Chain — farm inputs, logistics & distribution",
        "resource_kinds": [
            "input_order",
            "shipment",
            "storage_bin",
            "quality_check",
            "delivery_route",
        ],
        "domain_tags": ["agriculture", "supply_chain", "logistics"],
        "confusable_with": "agri.crops enterprise.project_mgmt",
    },
    {
        "name": "agri.weather",
        "os_domain": "agri",
        "apps": "AgriOS Weather — field-level weather monitoring & alerts",
        "resource_kinds": [
            "weather_forecast",
            "frost_alert",
            "rain_gauge",
            "degree_day",
            "spray_window",
        ],
        "domain_tags": ["agriculture", "weather", "monitoring"],
        "confusable_with": "agri.crops family.reminders",
    },
    {
        "name": "agri.compliance",
        "os_domain": "agri",
        "apps": "AgriOS Compliance — food safety, organic & regulatory",
        "resource_kinds": [
            "compliance_report",
            "inspection_log",
            "certification",
            "audit_trail",
            "pesticide_log",
        ],
        "domain_tags": ["agriculture", "compliance", "food_safety"],
        "confusable_with": "gov.permits agri.crops",
    },
    # ══════════════════════════════════════════════════════════════════════
    # PharmaOS (6 native apps) — Pharmacy Operations OS
    # ══════════════════════════════════════════════════════════════════════
    {
        "name": "pharma.prescriptions",
        "os_domain": "pharma",
        "apps": "PharmaOS Prescriptions — prescription processing & verification",
        "resource_kinds": [
            "prescription",
            "refill_request",
            "prior_auth",
            "drug_interaction",
            "dosage_instruction",
        ],
        "domain_tags": ["pharmacy", "prescriptions", "medication"],
        "confusable_with": "health.medications pharma.inventory",
    },
    {
        "name": "pharma.inventory",
        "os_domain": "pharma",
        "apps": "PharmaOS Inventory — drug stock, ordering & expiration",
        "resource_kinds": [
            "drug_stock",
            "order",
            "expiration_date",
            "controlled_substance_log",
            "supplier",
        ],
        "domain_tags": ["pharmacy", "inventory", "supply"],
        "confusable_with": "pharma.prescriptions agri.supply_chain",
    },
    {
        "name": "pharma.compliance",
        "os_domain": "pharma",
        "apps": "PharmaOS Compliance — DEA, FDA & state board reporting",
        "resource_kinds": [
            "dea_report",
            "fda_adverse_event",
            "state_filing",
            "audit_log",
            "dispensing_record",
        ],
        "domain_tags": ["pharmacy", "compliance", "regulation"],
        "confusable_with": "bank.compliance agri.compliance",
    },
    {
        "name": "pharma.patients",
        "os_domain": "pharma",
        "apps": "PharmaOS Patients — patient profiles, allergies & counseling",
        "resource_kinds": [
            "patient_profile",
            "allergy",
            "medication_history",
            "counseling_note",
            "adherence_record",
        ],
        "domain_tags": ["pharmacy", "patients", "care"],
        "confusable_with": "health.records pharma.prescriptions",
    },
    {
        "name": "pharma.ordering",
        "os_domain": "pharma",
        "apps": "PharmaOS Ordering — wholesale ordering & distributor management",
        "resource_kinds": [
            "purchase_order",
            "distributor",
            "backorder",
            "contract_price",
            "delivery_schedule",
        ],
        "domain_tags": ["pharmacy", "ordering", "procurement"],
        "confusable_with": "pharma.inventory agri.supply_chain",
    },
    {
        "name": "pharma.analytics",
        "os_domain": "pharma",
        "apps": "PharmaOS Analytics — dispensing trends, outcomes & reporting",
        "resource_kinds": [
            "dispensing_report",
            "outcome_metric",
            "trend_analysis",
            "benchmark",
            "dashboard",
        ],
        "domain_tags": ["pharmacy", "analytics", "reporting"],
        "confusable_with": "pharma.compliance enterprise.project_mgmt",
    },
]

# Total: 51 native apps across 8 OS domains

# ═══════════════════════════════════════════════════════════════════════════
# System Prompt — native-app classifier
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are generating training data for a NATIVE-APP intent classifier.
The classifier routes user queries to the correct NATIVE APP within an operating
system domain (FamilyOS, HealthOS, FinanceOS, etc.).  External services like Walmart,
Costco, Epic, Cerner are DATA BACKENDS — invisible to the classifier.

The classifier predicts THREE fields:
  effect: create | read | update | delete | complete | execute
  resource_kind: the noun the native app operates on
  native_app: the specific native app that handles this query (e.g., family.shopping)

=== EFFECT RULES (universal) ===
1. add/new/create/pay/send/file/submit/log/schedule/start/book = CREATE
2. show/list/get/check/what/did/how much/do I have/status = READ
3. change/update/reschedule/reassign/push/move/rename/modify/adjust = UPDATE
4. remove/delete/cancel/dismiss/void/close = DELETE
5. cross off/tick off/mark done/finished/completed/done = COMPLETE
6. turn on/off/activate/trigger/run/start/stop/execute = EXECUTE

=== NATIVE-APP RULES ===
- The query routes to the NATIVE APP, not the backend brand mentioned.
  "order from Walmart" → family.shopping (Walmart is a backend)
  "check my blood pressure on Fitbit" → health.vitals (Fitbit is a backend)
- Brand names in queries are backend hints, not routing targets.
- Cross-OS disambiguation: "schedule medication" → health.medications (not family.calendar)

=== THIS BATCH: {vertical_name} ===
OS Domain: {os_domain}
App description: {apps}
Resource kinds: {resource_kinds}
Domain tags: {domain_tags}
Most often confused with: {confusable_with}

DIFFICULTY DISTRIBUTION (STRICT):
- 0% easy
- 30% medium (indirect phrasing, synonym, casual speech)
- 40% hard (confusable pairs, boundary violations, misleading words)
- 30% hardest (brand-name queries that should route to native app, typos, slang)

NOISE (at least 25% of examples):
- Typos: swap/chop letters, phonetic spelling
- Slang: "grab" "nuke" "zap" "kill the" "scoop up" "snag"
- Incomplete: "um...", "oh yeah also...", "wait actually..."
- ALL-CAPS emphasis on one key word
- Brand names in query: "from Walmart" "on Fitbit" "via Epic" — route to natixcve app NOT backend

OUTPUT: pure JSON array, no markdown.
[
  {{
    "query": "grab my meds refill from the Walgreens app",
    "effect": "create",
    "resource_kind": "refill",
    "native_app": "health.medications",
    "difficulty": "hard",
    "note": "Walgreens is a pharmacy backend, routes to health.medications not pharma.*"
  }}
]

Generate {count} examples. Follow ALL rules. Return ONLY the JSON array."""  # noqa: E501


# ═══════════════════════════════════════════════════════════════════════════
# JSON Parser
# ═══════════════════════════════════════════════════════════════════════════


def parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    for prefix in ("```json", "```"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    start = raw.find("[")
    if start < 0:
        return []
    depth, end = 0, -1
    for i in range(start, len(raw)):
        if raw[i] == "[":
            depth += 1
        elif raw[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return []
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Validator — auto-fixes common labeling errors
# ═══════════════════════════════════════════════════════════════════════════


def validate(ex: dict) -> tuple[bool, str]:
    for k in ("query", "effect", "resource_kind", "native_app"):
        if not isinstance(ex.get(k), str) or not ex[k]:
            return False, f"missing {k}"

    q = ex["query"].lower()
    effect = ex["effect"]

    if effect not in EFFECTS:
        return False, f"bad effect: {effect}"

    cross_off_words = (
        "cross off",
        "tick off",
        "mark done",
        "mark as done",
        "finished",
        "completed",
        "check off",
        "checked off",
    )
    create_words = (
        "add ",
        "put ",
        "new ",
        "create ",
        "schedule ",
        "set up ",
        "make a ",
        "start a ",
        "log ",
        "record ",
        "send ",
        "pay ",
        "file ",
        "submit ",
        "book ",
    )
    update_words = (
        "change ",
        "update ",
        "modify",
        "reschedule",
        "rename",
        "adjust ",
        "edit ",
        "push ",
        "move ",
        "reassign",
        "delegate",
    )

    if effect == "delete" and any(w in q for w in cross_off_words):
        ex["effect"] = "complete"
        ex["note"] = ((ex.get("note") or "") + " AUTO-FIX: delete→complete").strip()
        return True, "auto-fixed"

    if (
        effect == "update"
        and any(w in q for w in create_words)
        and not any(w in q for w in update_words)
    ):
        if "setting" not in (ex.get("resource_kind") or ""):
            ex["effect"] = "create"
            ex["note"] = ((ex.get("note") or "") + " AUTO-FIX: update→create").strip()
            return True, "auto-fixed"

    return True, "ok"


# ═══════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════


def generate(
    project_id: str,
    location: str,
    total_count: int,
    batch_size: int = 15,
    resume: bool = False,
) -> tuple[list[dict], int]:
    client = genai.Client(vertexai=True, project=project_id, location=location)
    output_dir = _REPO_ROOT / "data" / "intent_schema"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "training_data.jsonl"

    batches_per_vertical = max(1, total_count // (len(DOMAIN_VERTICALS) * batch_size))
    target_per_vertical = batches_per_vertical * batch_size

    # ── Resume: count existing examples per native_app, skip completed verticals ──
    existing_counts: dict[str, int] = {}
    if resume and output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        ex = json.loads(line)
                        na = ex.get("native_app", "")
                        existing_counts[na] = existing_counts.get(na, 0) + 1
                    except json.JSONDecodeError:
                        pass
        if existing_counts:
            print(
                f"Resume mode: found {sum(existing_counts.values())} existing examples "
                f"across {len(existing_counts)} native apps"
            )

    print(f"Verticals: {len(DOMAIN_VERTICALS)}")
    print(
        f"Per vertical: {batches_per_vertical} batches × ~{batch_size} examples "
        f"= ~{target_per_vertical}"
    )
    print(f"Output: {output_path}")
    print("=" * 60)

    all_examples: list[dict] = []
    total_batches = 0

    for vi, vertical in enumerate(DOMAIN_VERTICALS):
        vname = vertical["name"]
        existing = existing_counts.get(vname, 0)
        if resume and existing >= target_per_vertical:
            print(
                f"\n[{vi+1}/{len(DOMAIN_VERTICALS)}] {vname} — SKIPPED "
                f"(already has {existing} examples, target={target_per_vertical})"
            )
            continue
        elif resume and existing > 0:
            skip_batches = existing // batch_size
            print(
                f"\n[{vi+1}/{len(DOMAIN_VERTICALS)}] {vname} — RESUMING "
                f"(has {existing}, need {target_per_vertical}, skipping {skip_batches} batches)"
            )
        else:
            print(
                f"\n[{vi+1}/{len(DOMAIN_VERTICALS)}] {vname} "
                f"(confusable_with: {vertical['confusable_with']})"
            )

        start_batch = (existing // batch_size) if resume else 0
        for batch_i in range(start_batch, batches_per_vertical):
            config = genai_types.GenerateContentConfig(
                temperature=0.9,
                top_p=0.95,
                max_output_tokens=16384,
                system_instruction=SYSTEM_PROMPT.format(
                    vertical_name=vname,
                    os_domain=vertical.get("os_domain", ""),
                    apps=vertical["apps"],
                    resource_kinds=", ".join(vertical["resource_kinds"]),
                    domain_tags=", ".join(vertical["domain_tags"]),
                    confusable_with=vertical["confusable_with"],
                    count=batch_size,
                ),
            )

            user_prompt = (
                f"Generate {batch_size} {vname} examples. "
                f"Resource kinds: {', '.join(vertical['resource_kinds'][:5])}. "
                f"Oversample confusable pairs with {vertical['confusable_with']}."
            )

            t0 = time.perf_counter()
            for retry in range(5):
                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash-lite",
                        contents=user_prompt,
                        config=config,
                    )
                    break
                except Exception as e:
                    if "429" in str(e) and retry < 4:
                        wait = 60 * (2**retry)  # 1min, 2min, 4min, 8min
                        print(f"  429 hit — waiting {wait//60}min (retry {retry+1}/5)...")
                        time.sleep(wait)
                    else:
                        raise
            elapsed = time.perf_counter() - t0

            examples = parse_json_array(response.text or "")
            valid = []
            for e in examples:
                ok, _ = validate(e)
                if ok:
                    valid.append(e)

            all_examples.extend(valid)
            total_batches += 1

            # Save incrementally — append only new valid examples
            with open(output_path, "a", encoding="utf-8") as f:
                for ex in valid:
                    f.write(json.dumps(ex, ensure_ascii=False) + "\n")

            print(
                f"  batch {batch_i+1}: {len(examples)} raw, {len(valid)} valid, "
                f"total={len(all_examples)} ({elapsed:.0f}s)"
            )

            # Normal delay between batches (retry handles 429 separately)
            if not (vi == len(DOMAIN_VERTICALS) - 1 and batch_i == batches_per_vertical - 1):
                time.sleep(3)

    # Dedup: read back appended file, dedup, rewrite
    with open(output_path, encoding="utf-8") as f:
        all_examples = [json.loads(line) for line in f if line.strip()]

    # Exact dedup
    seen: dict[str, dict] = {}
    for ex in all_examples:
        key = ex["query"].lower().strip()
        if key not in seen:
            seen[key] = ex
    all_examples = list(seen.values())

    # Near-duplicate dedup (82% similarity threshold)
    from difflib import SequenceMatcher

    deduped = []
    for ex in all_examples:
        q = ex["query"].lower().strip()
        is_dup = False
        for existing in deduped[-50:]:  # check last 50 for efficiency
            eq = existing["query"].lower().strip()
            if len(q) > 10 and len(eq) > 10 and SequenceMatcher(None, q, eq).ratio() > 0.82:
                is_dup = True
                break
        if not is_dup:
            deduped.append(ex)
    all_examples = deduped

    with open(output_path, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return all_examples, total_batches


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Universal Intent Schema Generator — Vertex AI")
    parser.add_argument("--count", type=int, default=4000)
    parser.add_argument("--batch", type=int, default=12)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip verticals that already have enough examples in output file",
    )
    parser.add_argument("--project", type=str, default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument(
        "--location", type=str, default=os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    )
    args = parser.parse_args()

    if not args.project:
        print("ERROR: Set GOOGLE_CLOUD_PROJECT env var")
        sys.exit(1)

    examples, batches = generate(
        args.project, args.location, args.count, args.batch, resume=args.resume
    )

    print(f"\n{'='*60}")
    print(f"Done: {len(examples)} examples in {batches} batches")
    print(f"{'='*60}")

    for label, field in [("Effect", "effect"), ("Difficulty", "difficulty")]:
        c = Counter(ex.get(field, "?") for ex in examples)
        print(f"\n{label}: {dict(c)}")

    # Native app coverage
    apps = Counter(ex.get("native_app", "?") for ex in examples)
    print(f"\nNative apps ({len(apps)} unique):")
    for a, c in apps.most_common(25):
        print(f"  {a}: {c}")

    # Confusable pair coverage
    print(f"\nConfusable pair coverage:")
    checks = {
        "remind_me→task": lambda ex: "remind me to" in ex["query"].lower()
        and ex.get("native_app", "") in ("family.tasks",),
        "running_low→shopping": lambda ex: any(
            w in ex["query"].lower() for w in ["running low", "out of", "we need more"]
        )
        and ex.get("native_app", "") in ("family.shopping",),
        "turn_off_feature→settings": lambda ex: any(
            w in ex["query"].lower()
            for w in [
                "predictor",
                "feature",
                "flag",
                "algorithm",
                "suggestions",
                "notification",
                "preference",
            ]
        )
        and ex.get("native_app", "") in ("family.family_settings",),
        "reassign→owner_domain": lambda ex: any(
            w in ex["query"].lower() for w in ["reassign", "delegate"]
        )
        and ex.get("effect", "") in ("update", "create"),
        "heads_up→reminders": lambda ex: any(
            w in ex["query"].lower()
            for w in ["heads up", "nudge", "ping me", "buzz me", "alert me"]
        )
        and ex.get("native_app", "") in ("family.reminders",),
        "dont_forget→tasks": lambda ex: "don't forget to" in ex["query"].lower()
        and ex.get("native_app", "") in ("family.tasks",),
        "cross_off→complete": lambda ex: any(
            w in ex["query"].lower() for w in ["cross off", "tick off", "mark done"]
        )
        and ex.get("effect", "") == "complete",
        "typo_present": lambda ex: any(
            w in ex["query"].lower()
            for w in ["shoping", "calander", "remined", "groseries", "mlk ", "dentst", "thes "]
        )
        or "..." in ex["query"],
    }
    for name, check_fn in checks.items():
        count = sum(1 for ex in examples if check_fn(ex))
        status = "OK" if count >= 20 else "NEED MORE"
        print(f"  [{status}] {name}: {count}")


if __name__ == "__main__":
    main()
