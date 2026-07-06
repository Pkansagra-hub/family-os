"""
POC v2: Benchmark Query Generator — Vertex AI
===============================================
Generates labeled benchmark queries for native-app routing eval.
Each LLM call produces ~70 queries for one native app across multiple tiers.

Query record shape:
  {{
    "id": "gen-{{app}}-{{n}}",
    "utterance": "raw user text",
    "expected_native_app": "family.shopping",
    "active_os_set": ["family", "health"],
    "tier": "direct | ambiguous | adversarial | backend_name | noisy | follow_up",
    "label_type": "hard_gold | ambiguous_envelope | context_required",
    "acceptable_apps": ["family.shopping", "family.tasks"],
    "must_include_top3": ["family.shopping", "family.tasks"],
    "backend_hints": ["walmart"],
    "rationale": "why this routes here"
  }}

Label types:
  - hard_gold: Exactly one correct app. No ambiguity.
  - ambiguous_envelope: Multiple apps valid. expected_native_app is best primary.
    acceptable_apps lists all valid apps. must_include_top3 says which MUST be in top-3.
  - context_required: Cannot resolve without prior conversation context.
    Include context array with prior turns.

Usage:
  $env:GOOGLE_CLOUD_PROJECT="project-33d51855-d616-4fcd-a69"
  $env:GOOGLE_CLOUD_LOCATION="global"
  python scripts/poc_v2/bench_query_generator.py --count 10000 --batch 70
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai
from google.genai import types as genai_types

# ═══════════════════════════════════════════════════════════════════════════
# Native App Registry — what apps exist and what they do
# ═══════════════════════════════════════════════════════════════════════════

NATIVE_APPS: list[dict] = [
    # FamilyOS
    {"id": "family.shopping", "os": "family", "desc": "Household grocery & goods shopping aggregator", "resources": ["item", "shopping_list", "order", "price", "cart", "grocery"], "backends": ["walmart", "kroger", "costco", "target", "aldi", "instacart", "doordash"], "confusable_with": ["family.tasks", "family.chores", "finance.budgeting"]},
    {"id": "family.tasks", "os": "family", "desc": "Household task & to-do management", "resources": ["task", "todo", "assignment", "errand", "project", "deadline"], "backends": ["todoist", "ticktick", "trello", "asana", "clickup"], "confusable_with": ["family.chores", "family.reminders", "family.shopping", "enterprise.project_mgmt"]},
    {"id": "family.calendar", "os": "family", "desc": "Family schedule & event management", "resources": ["event", "appointment", "meeting", "booking", "schedule"], "backends": ["google-calendar", "outlook", "apple-calendar"], "confusable_with": ["family.reminders", "family.tasks", "health.appointments"]},
    {"id": "family.reminders", "os": "family", "desc": "Alerts, nudges & notifications", "resources": ["reminder", "alert", "notification", "nudge", "ping"], "backends": ["apple-reminders", "google-keep", "due", "medisafe"], "confusable_with": ["family.calendar", "family.tasks", "health.medications"]},
    {"id": "family.chores", "os": "family", "desc": "Household chore tracking & assignment", "resources": ["chore", "routine", "household_duty", "cleaning_task", "zone"], "backends": ["tody", "sweepy", "ourhome"], "confusable_with": ["family.tasks", "family.reminders", "family.shopping"]},
    {"id": "family.family_settings", "os": "family", "desc": "Family preferences, permissions & feature flags", "resources": ["setting", "preference", "feature_flag", "policy", "toggle", "config"], "backends": [], "confusable_with": ["family.shopping", "family.tasks"]},
    # HealthOS
    {"id": "health.records", "os": "health", "desc": "Unified health records across providers", "resources": ["health_record", "patient_history", "lab_result", "imaging_report", "referral", "allergy", "immunization"], "backends": ["epic-mychart", "cerner", "apple-health-records"], "confusable_with": ["health.lab_results", "health.insurance", "health.medications"]},
    {"id": "health.appointments", "os": "health", "desc": "Healthcare provider search & appointment booking", "resources": ["appointment", "provider", "availability_slot", "telehealth_session", "followup"], "backends": ["zocdoc", "epic-telehealth", "doxy-me", "amwell", "teladoc"], "confusable_with": ["family.calendar", "health.records", "health.insurance"]},
    {"id": "health.medications", "os": "health", "desc": "Prescription management, refills, drug interactions, vaccine schedule", "resources": ["prescription", "medication", "refill", "interaction", "dose", "vaccine"], "backends": ["cvs", "walgreens", "rite-aid", "capsule"], "confusable_with": ["family.reminders", "pharmaos.fulfillment", "health.records"]},
    {"id": "health.vitals", "os": "health", "desc": "Wearable & wellness data aggregation — BP, HR, sleep, activity", "resources": ["vital", "health_metric", "sleep_data", "activity_data", "health_goal"], "backends": ["fitbit", "apple-health", "garmin", "oura", "whoop", "withings"], "confusable_with": ["health.records", "family.reminders", "health.medications"]},
    {"id": "health.insurance", "os": "health", "desc": "Health insurance — coverage check, claims, cost estimation, in-network provider search", "resources": ["insurance_claim", "coverage", "deductible", "in_network_provider", "cost_estimate", "prior_authorization"], "backends": ["aetna", "unitedhealth", "blue-cross", "cigna", "medicare"], "confusable_with": ["finance.insurance", "health.records", "pharmaos.insurance"]},
    {"id": "health.caregiving", "os": "health", "desc": "Caregiver coordination — care plans, care team messaging, emergency contacts", "resources": ["care_plan", "care_team", "adl_log", "emergency_contact", "shared_record"], "backends": ["carezone", "caring-bridge"], "confusable_with": ["health.records", "family.tasks", "health.appointments"]},
    {"id": "health.lab_results", "os": "health", "desc": "Lab result aggregation, trending, and interpretation", "resources": ["lab_result", "lab_order", "reference_range", "trend", "lab_appointment", "blood_test"], "backends": ["labcorp", "quest-diagnostics", "bioreference"], "confusable_with": ["health.records", "health.medications", "health.vitals"]},
    # FinanceOS
    {"id": "finance.accounts", "os": "finance", "desc": "Unified financial accounts — balances, transactions, transfers, net worth", "resources": ["account", "balance", "transaction", "statement", "transfer", "net_worth"], "backends": ["chase", "bofa", "wells-fargo", "venmo", "paypal"], "confusable_with": ["finance.budgeting", "finance.investing"]},
    {"id": "finance.budgeting", "os": "finance", "desc": "Budget tracking, spending analysis, savings goals, bill negotiation", "resources": ["budget", "expense", "category", "spending_limit", "savings_goal", "bill", "cash_flow"], "backends": ["mint", "ynab", "everydollar", "copilot", "monarch"], "confusable_with": ["finance.accounts", "family.shopping", "finance.loans"]},
    {"id": "finance.investing", "os": "finance", "desc": "Investment portfolio aggregation — stocks, ETFs, crypto, retirement accounts", "resources": ["portfolio", "trade", "holding", "dividend", "gain_loss", "price_alert", "crypto"], "backends": ["robinhood", "fidelity", "vanguard", "schwab", "coinbase"], "confusable_with": ["finance.accounts"]},
    {"id": "finance.taxes", "os": "finance", "desc": "Tax document aggregation, filing, deduction tracking, refund status", "resources": ["tax_document", "filing", "deduction", "w2", "1099", "tax_return", "tax_refund"], "backends": ["turbotax", "hr-block", "irs"], "confusable_with": ["finance.accounts", "enterprise.payroll"]},
    {"id": "finance.insurance", "os": "finance", "desc": "Personal insurance — auto, home, life, renters policy management", "resources": ["insurance_policy", "premium", "claim", "coverage", "beneficiary", "auto_insurance", "home_insurance"], "backends": ["geico", "progressive", "state-farm", "allstate", "lemonade"], "confusable_with": ["health.insurance", "finance.accounts"]},
    {"id": "finance.loans", "os": "finance", "desc": "Loan management — mortgage, auto, student, personal loans, refinance", "resources": ["loan", "mortgage", "payment_schedule", "payoff_balance", "refinance", "auto_loan", "student_loan"], "backends": ["nelnet", "fedloan", "sofi", "lendingtree", "credible"], "confusable_with": ["finance.accounts", "finance.budgeting"]},
    # PharmaOS
    {"id": "pharmaos.fulfillment", "os": "pharma", "desc": "Prescription fulfillment — receive e-Rx, verify, fill, pharmacist review, pickup", "resources": ["prescription_order", "fill_queue", "dispensing", "pickup", "delivery", "pharmacist_review"], "backends": ["cvs", "walgreens", "rite-aid", "capsule", "alto"], "confusable_with": ["health.medications", "family.reminders", "pharmaos.insurance"]},
    {"id": "pharmaos.inventory", "os": "pharma", "desc": "Pharmacy inventory — stock levels, auto-reorder, cold chain, drug recalls", "resources": ["inventory", "stock_level", "reorder", "cold_chain", "lot_number", "controlled_substance"], "backends": ["mckesson", "cardinal", "amerisourcebergen"], "confusable_with": ["pharmaos.fulfillment", "pharmaos.compliance"]},
    {"id": "pharmaos.insurance", "os": "pharma", "desc": "Pharmacy insurance adjudication — claims, prior auth, copay, formulary, Medicare Part D", "resources": ["claim_adjudication", "prior_authorization", "copay", "formulary", "manufacturer_coupon", "medicare_part_d"], "backends": ["express-scripts", "cvs-caremark", "optumrx", "goodrx"], "confusable_with": ["health.insurance", "pharmaos.fulfillment"]},
    {"id": "pharmaos.customer", "os": "pharma", "desc": "Patient communication — ready notifications, pickup reminders, counseling notes, surveys", "resources": ["patient_notification", "pickup_reminder", "refill_reminder", "counseling_note", "satisfaction_survey", "pharmacy_hours"], "backends": [], "confusable_with": ["family.reminders", "pharmaos.fulfillment"]},
    {"id": "pharmaos.compliance", "os": "pharma", "desc": "Pharmacy regulatory compliance — DEA tracking, HIPAA audit, USP 797/800, error reporting", "resources": ["dea_log", "hipaa_audit", "board_compliance", "usp_797", "usp_800", "medication_error"], "backends": ["dea-csos", "arcos", "state-bop", "ismp"], "confusable_with": ["pharmaos.inventory"]},
    {"id": "pharmaos.compounding", "os": "pharma", "desc": "Compounding pharmacy — formulas, batch tracking, potency/sterility testing, custom packaging", "resources": ["compounding_formula", "batch", "beyond_use_date", "potency_test", "sterility_test", "compliance_packaging"], "backends": [], "confusable_with": ["pharmaos.fulfillment", "pharmaos.inventory"]},
    # EnterpriseOS
    {"id": "enterprise.hr", "os": "enterprise", "desc": "HR — employee records, PTO, performance reviews, recruiting, onboarding", "resources": ["employee", "leave_request", "review", "onboarding_task", "policy_document", "pto"], "backends": ["workday", "bamboohr", "gusto", "adp", "rippling"], "confusable_with": ["enterprise.payroll", "enterprise.crm"]},
    {"id": "enterprise.payroll", "os": "enterprise", "desc": "Payroll processing — salary, benefits, tax withholding, payslips, direct deposit", "resources": ["payroll_run", "salary", "tax_withholding", "payslip", "direct_deposit", "bonus"], "backends": ["adp", "gusto", "paychex", "quickbooks-payroll"], "confusable_with": ["enterprise.hr", "finance.taxes"]},
    {"id": "enterprise.project_mgmt", "os": "enterprise", "desc": "Project management — tickets, sprints, epics, milestones, backlog", "resources": ["project", "ticket", "sprint", "milestone", "epic", "backlog_item", "bug"], "backends": ["jira", "linear", "asana", "monday-com", "clickup"], "confusable_with": ["family.tasks", "enterprise.devops"]},
    {"id": "enterprise.crm", "os": "enterprise", "desc": "CRM — contacts, leads, deals, pipeline, customer health, renewals", "resources": ["contact", "lead", "deal", "opportunity", "account", "pipeline", "customer_health"], "backends": ["salesforce", "hubspot", "zoho", "pipedrive"], "confusable_with": ["enterprise.communication", "enterprise.project_mgmt"]},
    {"id": "enterprise.documentation", "os": "enterprise", "desc": "Documentation — wiki pages, knowledge articles, SOPs, templates, runbooks", "resources": ["document", "wiki_page", "knowledge_article", "folder", "template", "sop", "runbook"], "backends": ["confluence", "notion", "sharepoint", "google-drive"], "confusable_with": ["enterprise.project_mgmt", "enterprise.communication"]},
    {"id": "enterprise.communication", "os": "enterprise", "desc": "Business communication — messaging, channels, email, meetings, calls, presence", "resources": ["message", "channel", "thread", "email", "meeting", "call", "presence"], "backends": ["slack", "microsoft-teams", "discord", "zoom", "gmail", "outlook"], "confusable_with": ["enterprise.crm", "enterprise.documentation", "family.calendar"]},
    {"id": "enterprise.devops", "os": "enterprise", "desc": "DevOps — deployments, incidents, alerts, CI/CD pipelines, infrastructure, on-call", "resources": ["deployment", "incident", "alert", "pipeline", "build", "release", "infrastructure", "on_call"], "backends": ["pagerduty", "datadog", "github-actions", "gitlab-ci", "aws", "gcp", "kubernetes"], "confusable_with": ["enterprise.project_mgmt", "enterprise.it"]},
    {"id": "enterprise.it", "os": "enterprise", "desc": "IT service management — tickets, assets, access reviews, security alerts, change requests", "resources": ["it_ticket", "asset", "access_review", "security_alert", "change_request", "vpn", "laptop"], "backends": ["servicenow", "jira-service-management", "okta", "azure-ad", "crowdstrike"], "confusable_with": ["enterprise.devops", "enterprise.communication"]},
]

NATIVE_APP_IDS = {a["id"] for a in NATIVE_APPS}
APP_BY_ID = {a["id"]: a for a in NATIVE_APPS}

# ═══════════════════════════════════════════════════════════════════════════
# System prompt
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are generating BENCHMARK QUERIES for a native-app router evaluation.

The router routes raw user utterances to the correct NATIVE APP. External services
(Walmart, CVS, Fitbit, Slack, etc.) are DATA BACKENDS — they go in backend_hints,
NEVER as expected_native_app.

=== CRITICAL: ANTI-BIAS RULES ===
DO NOT label everything as {app_id} just because this batch is for {app_id}.
- Generate queries that LOOK like they should route to {app_id} but actually route
  to one of its CONFUSABLE_WITH apps. These are your best test cases.
- Generate queries that mention concepts from OTHER domains but route here.
- If an existing kernel benchmark would route a query differently than your label,
  EXPLAIN why in the rationale.
- For genuinely ambiguous queries, use label_type="ambiguous_envelope" and list
  ALL valid apps in acceptable_apps.

=== ANTI-BIAS EXAMPLES ===
Batch for family.calendar → generate queries that:
  - Mention "doctor appointment" but route to health.appointments
  - Say "remind me about" but route to family.reminders
  - Say "schedule a" but route to health.appointments not calendar
Batch for family.reminders → generate queries that:
  - Mention "medication" but route to health.medications
  - Say "take my pills" → ambiguous_envelope with health.medications + family.reminders
Batch for health.medications → generate queries that:
  - Mention "Walgreens" / "pick up" but route to pharmaos.fulfillment
  - Say "text me when ready" → ambiguous with pharmaos.customer

=== LABEL TYPES ===
1. hard_gold: Exactly one correct app. No ambiguity. Use for direct, clear queries.
2. ambiguous_envelope: Multiple apps valid. Set expected_native_app to the BEST
   primary. List ALL valid apps in acceptable_apps. List apps that MUST appear
   in top-3 in must_include_top3.
3. context_required: Cannot resolve without prior conversation. Include a context
   array with prior user turns.

=== QUERY TIERS (vary these) ===
1. direct (20%): Clear intent, one obvious native app. label_type=hard_gold.
2. ambiguous (25%): Confusable with another app. label_type=ambiguous_envelope.
   Include acceptable_apps and must_include_top3.
3. adversarial (20%): Misleading words, backend names that sound like apps,
   vocabulary from wrong domain. Tests if router is fooled.
4. backend_name (15%): Query explicitly mentions a backend brand BY NAME.
   "refill my prescription at CVS" → health.medications, backend_hints=["cvs"]
   The backend name goes in backend_hints, NEVER in expected_native_app.
5. noisy (10%): Typos, slang, incomplete sentences, ALL-CAPS.
6. follow_up (10%): Context-dependent. label_type=context_required. Include
   context array with 1-3 prior user turns.

=== ACTIVE OS SETS (vary these) ===
- {{"family"}} — family user, only FamilyOS visible
- {{"family", "health"}} — family + health consent
- {{"family", "finance"}} — family + finance
- {{"family", "health", "pharma"}} — full healthcare stack
- {{"enterprise"}} — work user, only EnterpriseOS
- {{"health"}} — doctor/clinical user
- {{"pharma"}} — pharmacist user

=== CRITICAL RULES ===
1. expected_native_app MUST be exactly one of the native app IDs listed below.
2. backend_hints MUST contain backend brand names mentioned in the query.
3. Backend names in the query NEVER change expected_native_app.
4. For ambiguous queries, use label_type="ambiguous_envelope" with acceptable_apps.
5. active_os_set must INCLUDE the OS domain of expected_native_app.
6. NEVER generate a query where expected_native_app is a backend service.
7. At least 30% of queries should route to apps OTHER than {app_id} (confusable_with apps).
8. At least 15% of queries should be label_type="ambiguous_envelope".

=== THIS BATCH ===
Primary App: {app_id} ({os_domain})
Description: {desc}
Resource kinds: {resources}
Backend services (NOT routing targets): {backends}
Most confusable with: {confusable_with}
Other active OS domains available: {other_os}

Generate {count} diverse benchmark queries. At least 30% must route to confusable apps
NOT {app_id}. At least 15% must be ambiguous_envelope.

Return ONLY a JSON array. Each element:
{{
  "id": "{app_id}-N",
  "utterance": "user's raw text",
  "expected_native_app": "the.app.id",
  "active_os_set": ["os1", "os2"],
  "tier": "direct|ambiguous|adversarial|backend_name|noisy|follow_up",
  "label_type": "hard_gold|ambiguous_envelope|context_required",
  "acceptable_apps": ["app1", "app2"],
  "must_include_top3": ["app1"],
  "backend_hints": ["backend_name_if_any"],
  "context": [{{"role": "user", "text": "prior turn"}}],
  "rationale": "one sentence why this routes here"
}}"""


# ═══════════════════════════════════════════════════════════════════════════
# JSON parser
# ═══════════════════════════════════════════════════════════════════════════

def parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    for prefix in ("```json", "```"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
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
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Validator
# ═══════════════════════════════════════════════════════════════════════════

VALID_TIERS = {"direct", "ambiguous", "adversarial", "backend_name", "noisy", "follow_up"}
VALID_OS = {"family", "health", "finance", "pharma", "enterprise", "bank", "gov", "agri"}
VALID_LABEL_TYPES = {"hard_gold", "ambiguous_envelope", "context_required"}

# Label-consistency rules: if query mentions these keywords, flag as potential mislabel
# These are HEURISTICS, not hard gates — they raise warnings, not rejections
_LABEL_CONSISTENCY_CHECKS: dict[str, list[tuple[str, str]]] = {
    # "expected_app": [(keyword_phrase, "more_likely_app"), ...]
    "family.calendar": [
        ("doctor appointment", "health.appointments"),
        ("prescription refill", "health.medications"),
        ("blood pressure", "health.vitals"),
        ("physical exam", "health.appointments"),
    ],
    "family.reminders": [
        ("take my pills", "health.medications"),
        ("blood pressure", "health.vitals"),
        ("medication", "health.medications"),
        ("prescription", "health.medications"),
        ("refill", "health.medications"),
        ("dose", "health.medications"),
    ],
    "health.appointments": [
        ("groceries", "family.shopping"),
        ("homework", "family.tasks"),
        ("chores", "family.chores"),
    ],
    "health.medications": [
        ("pick up my prescription", "pharmaos.fulfillment"),
        ("text me when", "pharmaos.customer"),
        ("ready at pharmacy", "pharmaos.fulfillment"),
    ],
    "family.shopping": [
        ("budget", "finance.budgeting"),
        ("spending on", "finance.budgeting"),
    ],
}


def validate(ex: dict) -> tuple[bool, str]:
    """Validate a generated benchmark query. Returns (ok, reason)."""
    # Required fields
    for k in ("utterance", "expected_native_app", "active_os_set", "tier", "label_type"):
        if k not in ex:
            return False, f"missing {k}"

    # expected_native_app must be a real app
    if ex["expected_native_app"] not in NATIVE_APP_IDS:
        return False, f"bad app: {ex['expected_native_app']}"

    # tier must be valid
    if ex["tier"] not in VALID_TIERS:
        return False, f"bad tier: {ex['tier']}"

    # label_type must be valid
    lt = ex.get("label_type", "hard_gold")
    if lt not in VALID_LABEL_TYPES:
        return False, f"bad label_type: {lt}"

    # active_os_set must contain the app's OS domain
    app = APP_BY_ID.get(ex["expected_native_app"])
    if app and app["os"] not in ex["active_os_set"]:
        return False, f"os {app['os']} not in active_os_set {ex['active_os_set']}"

    # active_os_set must be valid domains
    for d in ex["active_os_set"]:
        if d not in VALID_OS:
            return False, f"bad os domain: {d}"

    # utterance must be non-empty string
    if not isinstance(ex.get("utterance"), str) or len(ex["utterance"]) < 3:
        return False, "utterance too short"

    # backend_hints must be list of strings
    hints = ex.get("backend_hints", [])
    if not isinstance(hints, list):
        return False, "backend_hints not a list"

    # backend_hints must NOT contain the expected_native_app
    for hint in hints:
        if hint.replace("-", "").replace(" ", "") in ex["expected_native_app"].replace(".", ""):
            return False, f"backend_hint '{hint}' looks like native app ID"

    # ── Label consistency: ambiguous_envelope MUST have acceptable_apps ──
    if lt == "ambiguous_envelope":
        acceptable = ex.get("acceptable_apps", [])
        if not isinstance(acceptable, list) or len(acceptable) < 2:
            return False, "ambiguous_envelope requires acceptable_apps with >=2 apps"
        for a in acceptable:
            if a not in NATIVE_APP_IDS:
                return False, f"bad acceptable_app: {a}"
        # expected_native_app should be in acceptable_apps
        if ex["expected_native_app"] not in acceptable:
            ex["acceptable_apps"].append(ex["expected_native_app"])

    # ── Label consistency: context_required MUST have context ──
    if lt == "context_required":
        ctx = ex.get("context", [])
        if not isinstance(ctx, list) or len(ctx) < 1:
            return False, "context_required requires context array with prior turns"

    # ── Label-consistency WARNING (not error) ──
    # Check if utterance keywords suggest a different app than expected
    utterance_lower = ex["utterance"].lower()
    expected = ex["expected_native_app"]
    checks = _LABEL_CONSISTENCY_CHECKS.get(expected, [])
    for keyword, more_likely in checks:
        if keyword in utterance_lower:
            # This is a WARNING — don't reject, but log it
            ex["_consistency_warning"] = f"'{keyword}' suggests {more_likely} over {expected}"

    # Generate ID if missing
    if "id" not in ex or not ex["id"]:
        ex["id"] = f"gen-{ex['expected_native_app']}"

    # Ensure acceptable_apps and must_include_top3 exist
    if "acceptable_apps" not in ex:
        ex["acceptable_apps"] = []
    if "must_include_top3" not in ex:
        ex["must_include_top3"] = []
    if "context" not in ex:
        ex["context"] = []

    return True, "ok"


# ═══════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate(
    project_id: str,
    location: str,
    total_count: int,
    batch_size: int = 70,
    resume: bool = False,
) -> tuple[list[dict], int]:
    client = genai.Client(vertexai=True, project=project_id, location=location)
    output_dir = _REPO_ROOT / "data" / "poc_v2"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "generated_bench_queries.jsonl"

    batches_per_app = max(1, total_count // (len(NATIVE_APPS) * batch_size))
    target_per_app = batches_per_app * batch_size

    # Resume support
    existing_counts: dict[str, int] = {}
    if resume and output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        ex = json.loads(line)
                        na = ex.get("expected_native_app", "")
                        existing_counts[na] = existing_counts.get(na, 0) + 1
                    except json.JSONDecodeError:
                        pass
        if existing_counts:
            print(f"Resume: {sum(existing_counts.values())} existing, {len(existing_counts)} apps")

    print(f"Apps: {len(NATIVE_APPS)}")
    print(f"Per app: {batches_per_app} batches x ~{batch_size} = ~{target_per_app}")
    print(f"Total target: ~{len(NATIVE_APPS) * target_per_app}")
    print(f"Output: {output_path}")
    print("=" * 60)

    all_examples: list[dict] = []
    total_batches = 0

    for ai, app in enumerate(NATIVE_APPS):
        app_id = app["id"]
        existing = existing_counts.get(app_id, 0)
        if resume and existing >= target_per_app:
            print(f"\n[{ai+1}/{len(NATIVE_APPS)}] {app_id} — SKIPPED ({existing} existing)")
            continue

        other_os = sorted(set(a["os"] for a in NATIVE_APPS if a["os"] != app["os"]))
        other_os_str = ", ".join(other_os[:4])

        start_batch = (existing // batch_size) if resume else 0
        for batch_i in range(start_batch, batches_per_app):
            config = genai_types.GenerateContentConfig(
                temperature=0.9,
                top_p=0.95,
                max_output_tokens=16384,
                system_instruction=SYSTEM_PROMPT.format(
                    app_id=app_id,
                    os_domain=app["os"],
                    desc=app["desc"],
                    resources=", ".join(app["resources"]),
                    backends=", ".join(app.get("backends", [])[:8]),
                    confusable_with=", ".join(app.get("confusable_with", [])),
                    other_os=other_os_str,
                    count=batch_size,
                ),
            )

            user_prompt = (
                f"Generate {batch_size} benchmark queries for this batch. "
                f"Primary app: {app_id}. "
                f"ANTI-BIAS: at least 30% must route to confusable apps ({', '.join(app.get('confusable_with', [])[:4])}), "
                f"not {app_id}. At least 15% must be ambiguous_envelope with acceptable_apps. "
                f"Generate queries that LOOK like {app_id} but actually route to confusable_with apps. "
                f"Vary active_os_set. Backend names go in backend_hints, never expected_native_app."
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
                        wait = 60 * (2 ** retry)
                        print(f"  429 — waiting {wait//60}min (retry {retry+1}/5)...")
                        time.sleep(wait)
                    else:
                        raise
            elapsed = time.perf_counter() - t0

            examples = parse_json_array(response.text or "")
            valid = []
            warnings_count = 0
            for i, e in enumerate(examples):
                ok, reason = validate(e)
                if ok:
                    # Ensure unique ID
                    if "id" not in e or not e["id"]:
                        e["id"] = f"gen-{app_id}-{batch_i * batch_size + i:04d}"
                    if "_consistency_warning" in e:
                        warnings_count += 1
                    valid.append(e)
                else:
                    print(f"    INVALID[{i}]: {reason} — {str(e.get('utterance', ''))[:60]}")

            all_examples.extend(valid)
            total_batches += 1

            # Append to file
            with open(output_path, "a", encoding="utf-8") as f:
                for ex in valid:
                    f.write(json.dumps(ex, ensure_ascii=False) + "\n")

            # Count label types in this batch
            lt_counts: dict[str, int] = {}
            for ex in valid:
                lt = ex.get("label_type", "hard_gold")
                lt_counts[lt] = lt_counts.get(lt, 0) + 1
            # Count how many route to other apps (not the primary for this batch)
            other_apps = sum(1 for ex in valid if ex["expected_native_app"] != app_id)

            print(
                f"  batch {batch_i+1}: {len(examples)} raw, {len(valid)} valid "
                f"({other_apps} other-app, {lt_counts.get('ambiguous_envelope', 0)} ambig, "
                f"{warnings_count} warns), total={len(all_examples)} ({elapsed:.0f}s)"
            )

            if not (ai == len(NATIVE_APPS) - 1 and batch_i == batches_per_app - 1):
                time.sleep(3)

    # Dedup
    with open(output_path, encoding="utf-8") as f:
        all_examples = [json.loads(line) for line in f if line.strip()]

    seen: dict[str, dict] = {}
    for ex in all_examples:
        key = ex["utterance"].lower().strip()
        if key not in seen:
            seen[key] = ex
    all_examples = list(seen.values())

    # Near-duplicate dedup
    deduped = []
    for ex in all_examples:
        q = ex["utterance"].lower().strip()
        is_dup = False
        for existing in deduped[-100:]:
            eq = existing["utterance"].lower().strip()
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
    parser = argparse.ArgumentParser(description="Benchmark Query Generator — Vertex AI")
    parser.add_argument("--count", type=int, default=5000, help="Target total queries")
    parser.add_argument("--batch", type=int, default=70, help="Queries per LLM call")
    parser.add_argument("--resume", action="store_true", help="Skip apps already at target")
    parser.add_argument("--project", type=str, default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--location", type=str, default=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))
    parser.add_argument("--validate-only", type=str, default="", help="Validate existing file")
    args = parser.parse_args()

    if not args.project:
        print("ERROR: GOOGLE_CLOUD_PROJECT not set.")
        print("  $env:GOOGLE_CLOUD_PROJECT='your-project-id'")
        sys.exit(1)

    if args.validate_only:
        path = Path(args.validate_only)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            examples = [json.loads(line) for line in f if line.strip()]
        ok = 0
        warns = 0
        for e in examples:
            is_ok, _ = validate(e)
            if is_ok:
                ok += 1
                if "_consistency_warning" in e:
                    warns += 1
        print(f"Validated {path}: {ok}/{len(examples)} valid, {warns} consistency warnings")
        by_tier: dict[str, int] = {}
        by_lt: dict[str, int] = {}
        for e in examples:
            by_tier[e.get("tier", "?")] = by_tier.get(e.get("tier", "?"), 0) + 1
            by_lt[e.get("label_type", "hard_gold")] = by_lt.get(e.get("label_type", "hard_gold"), 0) + 1
        print(f"Tiers: {dict(sorted(by_tier.items()))}")
        print(f"Label types: {dict(sorted(by_lt.items()))}")
        if warns > 0:
            print(f"\n⚠️  Consistency warnings ({warns}):")
            for e in examples:
                if "_consistency_warning" in e:
                    print(f"  [{e.get('id','?')}] {e['utterance'][:70]} → {e['expected_native_app']}")
                    print(f"      {e['_consistency_warning']}")
        sys.exit(0)

    print(f"Target: {args.count} queries, batch size: {args.batch}")
    examples, batches = generate(
        project_id=args.project,
        location=args.location,
        total_count=args.count,
        batch_size=args.batch,
        resume=args.resume,
    )

    # Print summary
    by_app: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    by_os: dict[str, int] = {}
    by_label_type: dict[str, int] = {}
    consistency_warnings = 0
    for e in examples:
        by_app[e["expected_native_app"]] = by_app.get(e["expected_native_app"], 0) + 1
        by_tier[e.get("tier", "?")] = by_tier.get(e.get("tier", "?"), 0) + 1
        lt = e.get("label_type", "hard_gold")
        by_label_type[lt] = by_label_type.get(lt, 0) + 1
        if "_consistency_warning" in e:
            consistency_warnings += 1
        app = APP_BY_ID.get(e["expected_native_app"], {})
        os_domain = app.get("os", "?") if app else "?"
        by_os[os_domain] = by_os.get(os_domain, 0) + 1

    print(f"\n{'='*60}")
    print(f"Generated {len(examples)} queries, {batches} batches")
    print(f"Label-type distribution:")
    for lt, count in sorted(by_label_type.items()):
        pct = count / len(examples) * 100 if examples else 0
        print(f"  {lt}: {count} ({pct:.1f}%)")
    print(f"Consistency warnings: {consistency_warnings}")
    print(f"\nBy OS domain:")
    for os_d, count in sorted(by_os.items()):
        print(f"  {os_d}: {count}")
    print(f"\nBy tier:")
    for tier, count in sorted(by_tier.items()):
        print(f"  {tier}: {count}")
    print(f"\nTop apps:")
    for app_id, count in sorted(by_app.items(), key=lambda x: -x[1])[:10]:
        print(f"  {app_id}: {count}")


if __name__ == "__main__":
    main()
