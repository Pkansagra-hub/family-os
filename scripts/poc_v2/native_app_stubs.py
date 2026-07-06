"""
POC v2: Native-App Stub Definitions — 27 stubs across 4 OS domains
====================================================================
POC-grade stubs for non-FamilyOS native apps.  Each stub has enough
semantic surface (label + description + concept_aliases + operation_aliases)
for MiniLM cosine-similarity routing.

The 6 FamilyOS apps use REAL definitions from k1.tools.family.*.definition.
These 27 stubs fill in HealthOS, FinanceOS, PharmaOS, and EnterpriseOS.

Data sources:
  - scripts/intent_schema_generator.py  (DOMAIN_VERTICALS list)
  - k1/docs/future_family_apps_development.md  (full app descriptions)

Usage:
  python scripts/poc_v2/native_app_stubs.py --validate   # check all stubs
  python scripts/poc_v2/native_app_stubs.py --list       # print all stub IDs
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NativeAppStub:
    """Minimal stub for a native app — enough text surface for embedding search."""

    connector_id: str
    label: str
    description: str  # 100-300 chars — the main embedding signal
    concept_aliases: list[str]  # noun phrases users say
    operation_aliases: list[str]  # verb phrases users say
    os_domain: str  # "health" | "finance" | "pharma" | "enterprise"
    confusable_with: list[str]  # other native app IDs this is ambiguous with

    def to_document_text(self) -> str:
        """Build the searchable text that gets embedded."""
        parts: list[str] = [
            f"{self.label}. {self.description}",
            f"Concepts: {' '.join(self.concept_aliases)}",
            f"Operations: {' '.join(self.operation_aliases)}",
        ]
        return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# HealthOS (7 native apps)
# ═══════════════════════════════════════════════════════════════════════════

HEALTH_RECORDS = NativeAppStub(
    connector_id="health.records",
    label="HealthOS Records",
    description=(
        "Unified health records aggregator across all healthcare providers. "
        "Pulls patient history, lab results, imaging reports, immunizations, "
        "allergies, and conditions from Epic MyChart, Cerner, AthenaHealth, "
        "Apple Health Records, VA Health, and hospital patient portals. "
        "Generates emergency-ready patient summaries. HIPAA-compliant aggregation."
    ),
    concept_aliases=[
        "health record",
        "patient history",
        "medical record",
        "lab result",
        "imaging report",
        "immunization",
        "allergy",
        "diagnosis",
        "condition",
        "clinical note",
        "referral",
        "surgical history",
        "family history",
        "emergency profile",
        "medication history",
        "visit summary",
        "discharge summary",
    ],
    operation_aliases=[
        "get patient history",
        "reconcile medications",
        "get lab results",
        "get immunizations",
        "get allergies",
        "get imaging",
        "generate emergency profile",
        "share records",
        "view medical history",
        "check test results",
        "pull records from",
        "aggregate health data",
    ],
    os_domain="health",
    confusable_with=["health.lab_results", "health.insurance", "health.medications"],
)

HEALTH_APPOINTMENTS = NativeAppStub(
    connector_id="health.appointments",
    label="HealthOS Appointments",
    description=(
        "Healthcare appointment aggregator. Find providers by specialty, location, "
        "and insurance. Book appointments across connected provider systems including "
        "ZocDoc, hospital networks, and clinic portals. Schedule telehealth visits "
        "via Zoom Healthcare, Doxy.me, Epic Telehealth, Amwell, Teladoc. "
        "Check real-time availability and manage follow-ups."
    ),
    concept_aliases=[
        "doctor appointment",
        "provider",
        "specialist",
        "telehealth",
        "video visit",
        "follow-up",
        "annual physical",
        "checkup",
        "consultation",
        "referral visit",
        "available slot",
        "provider search",
        "clinic",
        "hospital visit",
    ],
    operation_aliases=[
        "find provider",
        "book appointment",
        "schedule visit",
        "check availability",
        "join telehealth",
        "reschedule appointment",
        "cancel appointment",
        "find specialist",
        "search doctor",
        "schedule follow-up",
        "book telehealth",
        "see doctor",
    ],
    os_domain="health",
    confusable_with=["family.calendar", "health.records", "health.caregiving"],
)

HEALTH_MEDICATIONS = NativeAppStub(
    connector_id="health.medications",
    label="HealthOS Medications",
    description=(
        "Medication management and prescription tracking. Aggregates active prescriptions "
        "from CVS, Walgreens, Rite Aid, Capsule, Alto, hospital pharmacies, and mail-order. "
        "Checks drug interactions against Drugs.com, FDA database, Epocrates, Micromedex. "
        "Compares prices via GoodRx, SingleCare, RxSaver. Manages refill requests, "
        "dose tracking, medication reminders, and vaccine scheduling per CDC guidelines."
    ),
    concept_aliases=[
        "prescription",
        "medication",
        "refill",
        "dose",
        "pill",
        "drug",
        "rx",
        "pharmacy",
        "vaccine",
        "immunization",
        "drug interaction",
        "side effect",
        "dosage",
        "medication schedule",
        "refill request",
        "prior authorization",
        "medication reminder",
        "pill reminder",
    ],
    operation_aliases=[
        "refill prescription",
        "renew medication",
        "check interactions",
        "compare prices",
        "request refill",
        "set medication reminder",
        "track dose",
        "view prescriptions",
        "check dosage",
        "get vaccine schedule",
        "refill my",
        "renew my",
        "take my medication",
        "missed dose",
        "prescription ready",
        "medication reminder",
    ],
    os_domain="health",
    confusable_with=["family.reminders", "pharmaos.fulfillment", "health.records"],
)

HEALTH_VITALS = NativeAppStub(
    connector_id="health.vitals",
    label="HealthOS Vitals",
    description=(
        "Vitals and wellness data aggregator. Pulls real-time health metrics from "
        "Fitbit, Apple Health, Garmin, Oura, Whoop, Withings, and Samsung Health. "
        "Tracks blood pressure, heart rate, sleep stages, activity, weight, BMI, "
        "blood oxygen, body temperature. Analyzes long-term trends and sets health goals "
        "synced across all connected devices and platforms."
    ),
    concept_aliases=[
        "vital sign",
        "blood pressure",
        "heart rate",
        "sleep data",
        "activity data",
        "weight",
        "BMI",
        "blood oxygen",
        "temperature",
        "health metric",
        "fitness tracker",
        "wearable",
        "step count",
        "calories burned",
        "resting heart rate",
        "heart rate variability",
        "sleep score",
        "workout data",
        "exercise log",
        "health goal",
    ],
    operation_aliases=[
        "check blood pressure",
        "get vitals",
        "view sleep data",
        "track activity",
        "set health goal",
        "get heart rate",
        "view trends",
        "check weight",
        "log workout",
        "monitor health",
        "check my",
        "how is my",
        "what's my blood pressure",
        "how did I sleep",
    ],
    os_domain="health",
    confusable_with=["health.records", "family.reminders", "health.medications"],
)

HEALTH_INSURANCE = NativeAppStub(
    connector_id="health.insurance",
    label="HealthOS Insurance",
    description=(
        "Health insurance navigator. Checks coverage for procedures and medications "
        "across Aetna, UnitedHealth, Blue Cross, Cigna, Humana, Medicare, Medicaid. "
        "Estimates out-of-pocket costs, finds in-network providers, files claims, "
        "tracks deductible and out-of-pocket maximum across plans. Generates and "
        "submits appeals for denied claims."
    ),
    concept_aliases=[
        "health insurance",
        "coverage",
        "claim",
        "deductible",
        "copay",
        "in-network",
        "out-of-pocket",
        "prior authorization",
        "explanation of benefits",
        "insurance plan",
        "premium",
        "referral",
        "pre-authorization",
        "appeal",
    ],
    operation_aliases=[
        "check coverage",
        "estimate cost",
        "find in-network",
        "file claim",
        "track deductible",
        "appeal denial",
        "check if covered",
        "find provider who takes",
        "compare plans",
        "review coverage",
        "submit claim",
        "check benefits",
    ],
    os_domain="health",
    confusable_with=["finance.insurance", "health.records", "health.medications"],
)

HEALTH_CAREGIVING = NativeAppStub(
    connector_id="health.caregiving",
    label="HealthOS Caregiving",
    description=(
        "Caregiver coordination platform. Creates and manages care plans across "
        "multiple providers. HIPAA-compliant secure messaging between caregivers, "
        "family members, and providers. Manages emergency contacts and ICE information. "
        "Tracks Activities of Daily Living (ADLs) for elderly and disabled care recipients. "
        "Shares specific health records with authorized caregivers via role-based access."
    ),
    concept_aliases=[
        "care plan",
        "caregiver",
        "care team",
        "home health",
        "elder care",
        "assisted living",
        "ADL",
        "daily living",
        "emergency contact",
        "ICE",
        "care coordination",
        "patient advocate",
        "home care",
        "nursing care",
        "respite care",
    ],
    operation_aliases=[
        "create care plan",
        "update care plan",
        "message care team",
        "share records",
        "manage emergency contacts",
        "track daily activities",
        "coordinate care",
        "invite caregiver",
        "find home care",
        "schedule caregiver",
        "check on mom",
        "check on dad",
    ],
    os_domain="health",
    confusable_with=["health.records", "family.tasks", "health.appointments"],
)

HEALTH_LAB_RESULTS = NativeAppStub(
    connector_id="health.lab_results",
    label="HealthOS Lab Results",
    description=(
        "Lab result aggregator and trend analyzer. Pulls results from LabCorp, "
        "Quest Diagnostics, BioReference, hospital labs, and at-home test kits. "
        "Provides plain-language interpretation with reference ranges. Tracks lab "
        "values over time with trend visualization. Schedules lab draw appointments "
        "and securely shares results with designated providers."
    ),
    concept_aliases=[
        "lab result",
        "blood test",
        "lab work",
        "diagnostic test",
        "lab report",
        "reference range",
        "lab value",
        "blood work",
        "urinalysis",
        "biopsy",
        "genetic test",
        "covid test",
        "cholesterol",
        "A1C",
        "blood panel",
        "metabolic panel",
        "thyroid test",
    ],
    operation_aliases=[
        "get lab results",
        "view test results",
        "interpret results",
        "trend lab values",
        "schedule lab draw",
        "share results with doctor",
        "check my labs",
        "compare lab results",
        "find lab location",
        "order lab test",
        "view my blood work",
    ],
    os_domain="health",
    confusable_with=["health.records", "health.medications", "health.vitals"],
)

# ═══════════════════════════════════════════════════════════════════════════
# FinanceOS (6 native apps)
# ═══════════════════════════════════════════════════════════════════════════

FINANCE_ACCOUNTS = NativeAppStub(
    connector_id="finance.accounts",
    label="FinanceOS Accounts",
    description=(
        "Unified financial accounts dashboard. Aggregates balances across all bank "
        "accounts, credit cards, and payment apps: Chase, Bank of America, Wells Fargo, "
        "Citi, US Bank, credit unions, Venmo, PayPal, Cash App, Apple Cash. "
        "Provides unified transaction feed, fund transfers between accounts, "
        "auto-categorization of spending, and real-time net worth calculation."
    ),
    concept_aliases=[
        "bank account",
        "checking",
        "savings",
        "balance",
        "transaction",
        "transfer",
        "deposit",
        "withdrawal",
        "statement",
        "net worth",
        "credit card",
        "debit card",
        "payment method",
        "linked account",
        "routing number",
        "account number",
    ],
    operation_aliases=[
        "check balance",
        "view transactions",
        "transfer money",
        "deposit check",
        "view statement",
        "calculate net worth",
        "link account",
        "categorize spending",
        "search transactions",
        "export statement",
        "check my balance",
        "how much in checking",
    ],
    os_domain="finance",
    confusable_with=["finance.budgeting", "finance.investing", "bank.accounts"],
)

FINANCE_BUDGETING = NativeAppStub(
    connector_id="finance.budgeting",
    label="FinanceOS Budgeting",
    description=(
        "Personal budgeting and spending tracker. Creates budgets synced across "
        "Mint, YNAB, EveryDollar, Copilot, Monarch, Simplifi. Tracks real-time "
        "spending against budget categories. Forecasts cash flow based on recurring "
        "bills. Manages savings goals and identifies bills that can be negotiated "
        "down via Billshark, Trim, Rocket Money."
    ),
    concept_aliases=[
        "budget",
        "spending",
        "expense",
        "category",
        "savings goal",
        "bill",
        "subscription",
        "recurring payment",
        "cash flow",
        "income",
        "paycheck",
        "over budget",
        "under budget",
        "monthly budget",
        "emergency fund",
    ],
    operation_aliases=[
        "create budget",
        "track spending",
        "set savings goal",
        "forecast cash flow",
        "negotiate bill",
        "compare spending",
        "adjust budget",
        "review budget",
        "categorize expense",
        "check budget",
        "over budget on",
        "spent too much on",
        "how much did I spend on",
        "budget for",
    ],
    os_domain="finance",
    confusable_with=["finance.accounts", "family.shopping", "finance.loans"],
)

FINANCE_INVESTING = NativeAppStub(
    connector_id="finance.investing",
    label="FinanceOS Investing",
    description=(
        "Investment portfolio aggregator. Unified view across Robinhood, Fidelity, "
        "Vanguard, Schwab, E*TRADE, Webull, M1 Finance, Betterment, Wealthfront, "
        "Acorns. Tracks time-weighted returns, asset allocation, tax-loss harvesting "
        "opportunities. Aggregates crypto holdings from Coinbase, Binance, Kraken, "
        "Gemini, MetaMask, Ledger. Monitors portfolio drift from target allocation."
    ),
    concept_aliases=[
        "portfolio",
        "investment",
        "stock",
        "bond",
        "ETF",
        "mutual fund",
        "dividend",
        "capital gain",
        "asset allocation",
        "retirement account",
        "IRA",
        "401k",
        "brokerage",
        "crypto",
        "Bitcoin",
        "trade",
        "market order",
        "limit order",
        "price alert",
    ],
    operation_aliases=[
        "view portfolio",
        "check investments",
        "place trade",
        "set price alert",
        "rebalance portfolio",
        "check returns",
        "view dividend",
        "track crypto",
        "analyze allocation",
        "tax loss harvest",
        "how are my investments",
        "what's my portfolio worth",
        "buy stock",
    ],
    os_domain="finance",
    confusable_with=["finance.accounts", "bank.accounts", "finance.budgeting"],
)

FINANCE_TAXES = NativeAppStub(
    connector_id="finance.taxes",
    label="FinanceOS Taxes",
    description=(
        "Tax preparation aggregator. Gathers W-2s, 1099s, 1098s from employer portals, "
        "brokerages, banks, mortgage servicers. Estimates taxes in real-time based on "
        "all connected financial data. Identifies missed deductions across accounts. "
        "Prepares and files returns via TurboTax, H&R Block, TaxAct, FreeTaxUSA. "
        "Tracks refund status via IRS Where's My Refund and state equivalents."
    ),
    concept_aliases=[
        "tax return",
        "W-2",
        "1099",
        "deduction",
        "tax refund",
        "tax bracket",
        "estimated tax",
        "filing",
        "IRS",
        "tax document",
        "mortgage interest",
        "charitable donation",
        "business expense",
        "tax credit",
        "withholding",
    ],
    operation_aliases=[
        "file taxes",
        "estimate tax",
        "gather tax documents",
        "find deductions",
        "track refund",
        "check refund status",
        "download W-2",
        "submit return",
        "calculate withholding",
        "prepare tax filing",
        "do my taxes",
    ],
    os_domain="finance",
    confusable_with=["finance.accounts", "govos.tax", "enterprise.payroll"],
)

FINANCE_INSURANCE = NativeAppStub(
    connector_id="finance.insurance",
    label="FinanceOS Insurance",
    description=(
        "Personal insurance policy manager. Aggregates auto, home, life, renters, "
        "and umbrella policies from GEICO, Progressive, State Farm, Allstate, "
        "Lemonade, Hippo, MetLife. Compares quotes across providers via Policygenius, "
        "Zebra, Insurify. Files claims, tracks renewals, and identifies bundling "
        "opportunities across insurers."
    ),
    concept_aliases=[
        "insurance policy",
        "auto insurance",
        "home insurance",
        "life insurance",
        "renters insurance",
        "umbrella policy",
        "premium",
        "deductible",
        "claim",
        "renewal",
        "quote",
        "bundling",
        "coverage limit",
        "beneficiary",
    ],
    operation_aliases=[
        "compare quotes",
        "file claim",
        "check coverage",
        "renew policy",
        "bundle policies",
        "update beneficiary",
        "get insurance quote",
        "review policy",
        "add vehicle",
        "change coverage",
        "is my car insured",
        "home insurance renewal",
    ],
    os_domain="finance",
    confusable_with=["health.insurance", "finance.accounts", "finance.loans"],
)

FINANCE_LOANS = NativeAppStub(
    connector_id="finance.loans",
    label="FinanceOS Loans",
    description=(
        "Loan management dashboard. Aggregates mortgages, auto loans, student loans, "
        "and personal loans across all servicers: mortgage servicers, Nelnet, FedLoan, "
        "Aidvantage, auto lenders, SoFi, LendingClub. Compares refinance rates via "
        "LendingTree, Credible, banks, credit unions. Projects payoff dates with "
        "extra payment scenarios and checks forbearance eligibility."
    ),
    concept_aliases=[
        "loan",
        "mortgage",
        "student loan",
        "auto loan",
        "personal loan",
        "refinance",
        "interest rate",
        "principal",
        "escrow",
        "payoff",
        "amortization",
        "forbearance",
        "deferment",
        "monthly payment",
        "debt",
        "credit score",
    ],
    operation_aliases=[
        "check loan balance",
        "make payment",
        "compare refinance rates",
        "calculate payoff",
        "request forbearance",
        "view amortization",
        "apply for refinance",
        "check interest rate",
        "pay extra principal",
        "simulate payoff",
        "how much left on mortgage",
    ],
    os_domain="finance",
    confusable_with=["finance.accounts", "bank.lending", "finance.budgeting"],
)

# ═══════════════════════════════════════════════════════════════════════════
# PharmaOS (6 native apps)
# ═══════════════════════════════════════════════════════════════════════════

PHARMAOS_FULFILLMENT = NativeAppStub(
    connector_id="pharmaos.fulfillment",
    label="PharmaOS Fulfillment",
    description=(
        "Prescription fulfillment and dispensing platform for pharmacies. Receives "
        "e-prescriptions from SureScripts, EPCS, and provider EHRs. Verifies medications "
        "via drug utilization review against Micromedex, Lexicomp, Epocrates, FDA. "
        "Manages fill workflow through pharmacy automation (ScriptPro, Parata, Omnicell). "
        "Handles pharmacist review queue, patient pickup verification, and home delivery "
        "logistics with cold chain management."
    ),
    concept_aliases=[
        "prescription fulfillment",
        "fill queue",
        "e-prescription",
        "pharmacy workflow",
        "pharmacist review",
        "dispensing",
        "pickup",
        "delivery",
        "cold chain",
        "label printing",
        "patient verification",
        "script",
        "order",
        "prescription order",
        "ready for pickup",
    ],
    operation_aliases=[
        "receive prescription",
        "verify medication",
        "fill prescription",
        "pharmacist review",
        "patient pickup",
        "delivery queue",
        "check fill status",
        "process refill",
        "dispense medication",
        "my prescription ready",
        "prescription status",
        "ready at pharmacy",
        "pick up prescription",
    ],
    os_domain="pharma",
    confusable_with=["health.medications", "family.reminders", "pharmaos.insurance"],
)

PHARMAOS_INVENTORY = NativeAppStub(
    connector_id="pharmaos.inventory",
    label="PharmaOS Inventory",
    description=(
        "Pharmacy inventory and supply chain management. Real-time stock levels across "
        "locations via wholesalers McKesson, Cardinal, AmerisourceBergen, and direct "
        "manufacturers. Auto-reorder based on par levels. Cold chain monitoring for "
        "biologics and vaccines with IoT sensors and compliance logs. Drug recall "
        "management and lot tracking via FDA, manufacturers. DEA Schedule II-V "
        "controlled substance tracking."
    ),
    concept_aliases=[
        "inventory",
        "stock level",
        "wholesaler",
        "reorder",
        "par level",
        "cold chain",
        "drug recall",
        "lot number",
        "controlled substance",
        "Schedule II",
        "expiration date",
        "return",
        "reverse distributor",
        "stock shortage",
        "backorder",
    ],
    operation_aliases=[
        "check stock",
        "auto reorder",
        "track inventory",
        "monitor cold chain",
        "process recall",
        "manage controlled substances",
        "process returns",
        "check expiration",
        "order from wholesaler",
        "reorder medication",
    ],
    os_domain="pharma",
    confusable_with=["pharmaos.fulfillment", "pharmaos.compliance", "enterprise.devops"],
)

PHARMAOS_INSURANCE = NativeAppStub(
    connector_id="pharmaos.insurance",
    label="PharmaOS Insurance",
    description=(
        "Pharmacy insurance adjudication engine. Real-time claim adjudication with "
        "PBMs (Express Scripts, CVS Caremark, OptumRx) and insurance payers. Submits "
        "and tracks prior authorization requests. Calculates patient copay and "
        "coinsurance. Applies manufacturer coupons and discount cards from GoodRx, "
        "SingleCare. Medicare Part D compliance and billing via CMS."
    ),
    concept_aliases=[
        "insurance adjudication",
        "PBM",
        "prior authorization",
        "copay",
        "coinsurance",
        "formulary",
        "manufacturer coupon",
        "discount card",
        "Medicare Part D",
        "billing",
        "claim",
        "rejection",
        "PA",
        "coverage determination",
    ],
    operation_aliases=[
        "adjudicate claim",
        "submit prior auth",
        "calculate copay",
        "apply coupon",
        "check formulary",
        "bill Medicare",
        "process insurance",
        "check coverage",
        "verify benefits",
        "how much will this cost with insurance",
    ],
    os_domain="pharma",
    confusable_with=["health.insurance", "pharmaos.fulfillment", "finance.insurance"],
)

PHARMAOS_CUSTOMER = NativeAppStub(
    connector_id="pharmaos.customer",
    label="PharmaOS Customer",
    description=(
        "Patient communication and engagement platform for pharmacies. Sends ready "
        "notifications via SMS, push, email, IVR. Manages pickup reminders and "
        "proactive refill reminders. Documents pharmacist counseling notes. Collects "
        "post-pickup satisfaction and medication adherence surveys. Manages patient "
        "preferences for communication channels and pharmacy location."
    ),
    concept_aliases=[
        "patient notification",
        "ready alert",
        "pickup reminder",
        "refill reminder",
        "counseling",
        "satisfaction survey",
        "adherence",
        "patient communication",
        "pharmacy hours",
        "pharmacy location",
        "wait time",
        "text alert",
    ],
    operation_aliases=[
        "notify patient",
        "send reminder",
        "text when ready",
        "call patient",
        "document counseling",
        "send survey",
        "check adherence",
        "manage preferences",
        "update contact",
        "what time does pharmacy close",
        "pharmacy hours",
        "contact pharmacy",
    ],
    os_domain="pharma",
    confusable_with=["family.reminders", "pharmaos.fulfillment", "health.caregiving"],
)

PHARMAOS_COMPLIANCE = NativeAppStub(
    connector_id="pharmaos.compliance",
    label="PharmaOS Compliance",
    description=(
        "Pharmacy regulatory compliance platform. DEA controlled substance inventory "
        "and dispensing logs (CSOS, ARCOS). HIPAA audit trail for all PHI access. "
        "State Board of Pharmacy compliance tracking. USP 797 sterile and USP 800 "
        "hazardous compounding compliance with environmental monitoring. Medication "
        "error reporting with root cause analysis and ISMP submission."
    ),
    concept_aliases=[
        "DEA compliance",
        "controlled substance",
        "HIPAA audit",
        "Board of Pharmacy",
        "USP 797",
        "USP 800",
        "sterile compounding",
        "hazardous drug",
        "medication error",
        "root cause analysis",
        "ISMP",
        "ARCOS",
        "regulatory inspection",
        "compliance report",
    ],
    operation_aliases=[
        "log controlled substance",
        "run audit trail",
        "file DEA report",
        "document error",
        "analyze root cause",
        "prepare for inspection",
        "monitor compliance",
        "track inventory log",
        "submit board report",
        "check regulatory status",
    ],
    os_domain="pharma",
    confusable_with=["pharmaos.inventory", "bank.compliance", "enterprise.it"],
)

PHARMAOS_COMPOUNDING = NativeAppStub(
    connector_id="pharmaos.compounding",
    label="PharmaOS Compounding",
    description=(
        "Compounding pharmacy management. Manages compounding formulas and recipes "
        "referenced against USP and professional references. Tracks compound batches "
        "by lot number and beyond-use date. Schedules and tracks potency and sterility "
        "testing via third-party labs. Manages custom packaging for compliance "
        "packaging and specialty preparations."
    ),
    concept_aliases=[
        "compounding",
        "formula",
        "recipe",
        "batch",
        "beyond-use date",
        "potency test",
        "sterility test",
        "compliance packaging",
        "specialty prep",
        "USP compound",
        "non-sterile compound",
        "flavoring",
        "suspension",
    ],
    operation_aliases=[
        "manage formula",
        "create batch",
        "track beyond-use date",
        "schedule testing",
        "order packaging",
        "compound medication",
        "verify formula",
        "log batch",
        "check potency",
        "test sterility",
    ],
    os_domain="pharma",
    confusable_with=["pharmaos.fulfillment", "pharmaos.inventory", "health.medications"],
)

# ═══════════════════════════════════════════════════════════════════════════
# EnterpriseOS (8 native apps)
# ═══════════════════════════════════════════════════════════════════════════

ENTERPRISE_HR = NativeAppStub(
    connector_id="enterprise.hr",
    label="EnterpriseOS HR",
    description=(
        "Human resources hub for employee management. Unified employee records across "
        "Workday, BambooHR, Gusto, ADP, Rippling, SAP SuccessFactors. Manages payroll, "
        "benefits enrollment, performance reviews (Lattice, 15Five, Culture Amp), "
        "recruiting pipeline (Greenhouse, Lever, LinkedIn), PTO calendar, and "
        "compliance training across all LMS platforms."
    ),
    concept_aliases=[
        "HR",
        "employee",
        "payroll",
        "benefits",
        "performance review",
        "recruiting",
        "PTO",
        "time off",
        "leave request",
        "onboarding",
        "compliance training",
        "org chart",
        "headcount",
        "termination",
        "promotion",
        "salary",
    ],
    operation_aliases=[
        "request PTO",
        "view pay stub",
        "enroll in benefits",
        "check leave balance",
        "submit performance review",
        "post job opening",
        "onboard employee",
        "update employee record",
        "approve time off",
        "check vacation days",
        "how many PTO days",
        "request time off",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.payroll", "enterprise.crm", "enterprise.communication"],
)

ENTERPRISE_PAYROLL = NativeAppStub(
    connector_id="enterprise.payroll",
    label="EnterpriseOS Payroll",
    description=(
        "Payroll and compensation management. Processes payroll runs across ADP, Gusto, "
        "Rippling, Paychex, QuickBooks Payroll. Manages salary data, benefit enrollments, "
        "tax withholding calculations, and payslip generation. Handles multi-state "
        "tax compliance and garnishment processing."
    ),
    concept_aliases=[
        "payroll",
        "salary",
        "compensation",
        "payslip",
        "pay stub",
        "tax withholding",
        "benefit enrollment",
        "garnishment",
        "bonus",
        "raise",
        "direct deposit",
        "pay period",
        "overtime",
    ],
    operation_aliases=[
        "run payroll",
        "view payslip",
        "update salary",
        "calculate withholding",
        "process bonus",
        "enroll benefits",
        "change direct deposit",
        "generate W-2",
        "view pay history",
        "check my pay",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.hr", "finance.taxes", "finance.accounts"],
)

ENTERPRISE_PROJECT_MGMT = NativeAppStub(
    connector_id="enterprise.project_mgmt",
    label="EnterpriseOS Project Management",
    description=(
        "Project and work tracking across teams. Manages projects, tickets, sprints, "
        "milestones, epics, and backlog items across Jira, Linear, Asana, Monday.com, "
        "ClickUp, Trello. Views sprint burndown, velocity reports, cumulative flow "
        "diagrams. Manages team capacity, WIP limits, and project roadmaps."
    ),
    concept_aliases=[
        "project",
        "ticket",
        "issue",
        "sprint",
        "milestone",
        "epic",
        "backlog",
        "task",
        "bug",
        "story",
        "Kanban",
        "Scrum",
        "velocity",
        "burndown",
        "capacity",
        "work item",
    ],
    operation_aliases=[
        "create ticket",
        "create issue",
        "start sprint",
        "complete sprint",
        "update status",
        "assign task",
        "move to done",
        "view board",
        "check sprint progress",
        "create epic",
        "file bug",
        "track project",
        "create a ticket for",
        "what's the status of",
    ],
    os_domain="enterprise",
    confusable_with=["family.tasks", "enterprise.devops", "enterprise.documentation"],
)

ENTERPRISE_CRM = NativeAppStub(
    connector_id="enterprise.crm",
    label="EnterpriseOS CRM",
    description=(
        "Customer relationship management hub. Aggregates customer data, leads, deals, "
        "and pipeline across Salesforce, HubSpot, Zoho, Pipedrive, Freshsales, Intercom, "
        "Zendesk. Computes composite customer health scores from support tickets, "
        "product usage, and billing data. Predicts renewals and identifies churn risk "
        "through cross-system analysis."
    ),
    concept_aliases=[
        "CRM",
        "customer",
        "lead",
        "deal",
        "opportunity",
        "pipeline",
        "contact",
        "account",
        "sales",
        "renewal",
        "churn",
        "customer health",
        "support ticket",
        "salesforce",
        "hubspot",
    ],
    operation_aliases=[
        "view customer",
        "update deal",
        "add lead",
        "check pipeline",
        "log activity",
        "create opportunity",
        "view account",
        "track renewal",
        "analyze churn",
        "update CRM",
        "find contact",
        "search customer",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.communication", "enterprise.project_mgmt", "bank.customer"],
)

ENTERPRISE_DOCUMENTATION = NativeAppStub(
    connector_id="enterprise.documentation",
    label="EnterpriseOS Documentation",
    description=(
        "Knowledge base and documentation management. Manages documents, wiki pages, "
        "knowledge articles, and templates across Confluence, Notion, SharePoint, "
        "Google Drive, Dropbox Paper, GitBook. Full-text search across all connected "
        "knowledge sources. Version history, collaborative editing, and access control."
    ),
    concept_aliases=[
        "document",
        "wiki",
        "knowledge base",
        "doc",
        "template",
        "page",
        "folder",
        "confluence",
        "notion",
        "sharepoint",
        "knowledge article",
        "SOP",
        "runbook",
        "playbook",
        "onboarding guide",
    ],
    operation_aliases=[
        "search docs",
        "create page",
        "update wiki",
        "find document",
        "share document",
        "organize folder",
        "create template",
        "view version history",
        "search knowledge base",
        "find the doc for",
        "where is the document about",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.project_mgmt", "enterprise.communication", "enterprise.hr"],
)

ENTERPRISE_COMMUNICATION = NativeAppStub(
    connector_id="enterprise.communication",
    label="EnterpriseOS Communication",
    description=(
        "Unified business communications platform. Sends and searches messages across "
        "Slack, Microsoft Teams, Discord, WhatsApp Business, Telegram. Schedules "
        "meetings with room and video availability across Google Calendar, Outlook, "
        "Zoom, Teams, Webex. Unified inbox across email and chat. Aggregated presence "
        "status across all connected platforms."
    ),
    concept_aliases=[
        "message",
        "chat",
        "channel",
        "thread",
        "email",
        "meeting",
        "call",
        "slack",
        "teams",
        "zoom",
        "inbox",
        "presence",
        "DM",
        "group chat",
        "video call",
        "conference",
    ],
    operation_aliases=[
        "send message",
        "schedule meeting",
        "search messages",
        "create channel",
        "share file",
        "start call",
        "check presence",
        "join meeting",
        "message the team",
        "ping channel",
        "set up a call",
        "schedule a meeting with",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.crm", "enterprise.documentation", "family.calendar"],
)

ENTERPRISE_DEVOPS = NativeAppStub(
    connector_id="enterprise.devops",
    label="EnterpriseOS DevOps",
    description=(
        "Developer operations and infrastructure management. Aggregates alerts and "
        "creates unified incidents from PagerDuty, OpsGenie, Datadog, Sentry, Grafana, "
        "CloudWatch. Tracks deployments across GitHub Actions, GitLab CI, CircleCI, "
        "Jenkins, ArgoCD, Spinnaker. Views infrastructure across AWS, GCP, Azure, "
        "Kubernetes clusters. Cross-cloud cost optimization and on-call scheduling."
    ),
    concept_aliases=[
        "deployment",
        "incident",
        "alert",
        "pipeline",
        "CI/CD",
        "infrastructure",
        "cloud",
        "AWS",
        "GCP",
        "Azure",
        "Kubernetes",
        "monitoring",
        "on-call",
        "PagerDuty",
        "runbook",
        "rollback",
        "build",
        "release",
    ],
    operation_aliases=[
        "deploy service",
        "rollback deployment",
        "acknowledge incident",
        "view alerts",
        "check build status",
        "run pipeline",
        "view infrastructure",
        "trigger deploy",
        "check on-call",
        "who's on call",
        "deploy to staging",
        "deploy to production",
        "is the build passing",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.project_mgmt", "enterprise.it", "bank.fraud"],
)

ENTERPRISE_IT = NativeAppStub(
    connector_id="enterprise.it",
    label="EnterpriseOS IT",
    description=(
        "IT service management platform. Aggregates IT tickets across ServiceNow, "
        "Jira Service Management, Zendesk, Freshservice, Ivanti. Manages hardware "
        "and software asset inventory. Reviews access across Okta, Azure AD, JumpCloud, "
        "Duo, SailPoint. Aggregates security alerts from CrowdStrike, SentinelOne, "
        "Splunk, Palo Alto, Wiz. Manages change advisory board (CAB) requests."
    ),
    concept_aliases=[
        "IT ticket",
        "service desk",
        "asset inventory",
        "access review",
        "security alert",
        "change request",
        "CAB",
        "Okta",
        "Active Directory",
        "laptop",
        "software license",
        "VPN",
        "firewall",
        "endpoint",
    ],
    operation_aliases=[
        "create ticket",
        "check ticket status",
        "review access",
        "approve change",
        "inventory asset",
        "investigate alert",
        "reset password",
        "provision laptop",
        "grant access",
        "revoke access",
        "IT help",
        "computer issue",
        "VPN not working",
    ],
    os_domain="enterprise",
    confusable_with=["enterprise.devops", "enterprise.communication", "bank.compliance"],
)

# ═══════════════════════════════════════════════════════════════════════════
# Master registry
# ═══════════════════════════════════════════════════════════════════════════

ALL_STUBS: dict[str, NativeAppStub] = {
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

# Map connector_id → os_domain (fast lookup)
STUB_OS_DOMAIN: dict[str, str] = {s.connector_id: s.os_domain for s in ALL_STUBS.values()}

# Map os_domain → list of connector_ids in that domain
STUBS_BY_DOMAIN: dict[str, list[str]] = {}
for _s in ALL_STUBS.values():
    STUBS_BY_DOMAIN.setdefault(_s.os_domain, []).append(_s.connector_id)


def validate() -> list[str]:
    """Validate all stubs. Returns list of issues (empty = clean)."""
    issues: list[str] = []
    seen_ids: set[str] = set()

    for stub in ALL_STUBS.values():
        # Duplicate check
        if stub.connector_id in seen_ids:
            issues.append(f"DUPLICATE: {stub.connector_id}")
        seen_ids.add(stub.connector_id)

        # Description length
        if len(stub.description) < 100:
            issues.append(f"SHORT_DESC: {stub.connector_id} ({len(stub.description)} chars)")

        # Concept aliases
        if len(stub.concept_aliases) < 8:
            issues.append(f"FEW_CONCEPTS: {stub.connector_id} ({len(stub.concept_aliases)})")

        # Operation aliases
        if len(stub.operation_aliases) < 6:
            issues.append(f"FEW_OPS: {stub.connector_id} ({len(stub.operation_aliases)})")

        # OS domain
        valid_domains = {
            "health",
            "finance",
            "pharma",
            "enterprise",
            "family",
            "bank",
            "gov",
            "agri",
        }
        if stub.os_domain not in valid_domains:
            issues.append(f"BAD_DOMAIN: {stub.connector_id} ({stub.os_domain})")

        # Confusable_with references real apps
        for ref in stub.confusable_with:
            if (
                ref not in ALL_STUBS
                and not ref.startswith("family.")
                and not ref.startswith("bank.")
                and not ref.startswith("govos.")
            ):
                issues.append(f"UNKNOWN_CONFUSABLE: {stub.connector_id} -> {ref}")

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
        print(f"  ✅ All {len(ALL_STUBS)} stubs valid.")
    elif "--list" in sys.argv:
        for stub in ALL_STUBS.values():
            print(f"  {stub.connector_id} ({stub.os_domain}) — {stub.label}")
    else:
        print(f"  {len(ALL_STUBS)} stub definitions loaded.")
        print(f"  Domains: {set(s.os_domain for s in ALL_STUBS.values())}")
        print(f"  HealthOS: {len(STUBS_BY_DOMAIN.get('health', []))}")
        print(f"  FinanceOS: {len(STUBS_BY_DOMAIN.get('finance', []))}")
        print(f"  PharmaOS: {len(STUBS_BY_DOMAIN.get('pharma', []))}")
        print(f"  EnterpriseOS: {len(STUBS_BY_DOMAIN.get('enterprise', []))}")
