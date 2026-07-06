"""GlobalProjectionStore — shared SQLite store for capabilities, connectors, graph ontology.

Phase 1, Epic 1 (Issues 1.1–1.4).  The single source of truth for all
capability contracts, connector manifests, constitutions, resource kinds,
and the 6 graph ontology tables that power typed resolution.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epics 1.1–1.4.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Issue 1.1 — Record dataclasses (return types for all query methods)
# ---------------------------------------------------------------------------


@dataclass
class ConnectorRecord:
    connector_id: str
    label: str
    connector_type: str  # 'native' | 'bridge' | 'ifl'
    provider_type: str  # 'LOCAL' | 'MCP' | 'BRIDGE' | 'AGENT' | 'WORKFLOW'
    version: str
    admission_verdict: str  # 'admitted' | 'pending' | 'rejected'
    registration_type: str  # 'static' | 'dynamic' | 'discovered'
    constitution: dict = field(default_factory=dict)
    policy_declarations: dict = field(default_factory=dict)
    resource_kinds: list[str] = field(default_factory=list)
    guide_cards: list[dict] = field(default_factory=list)  # Phase 1.1 (Epic 9.5)
    domain_id: str = ""  # Phase 2.6 (Epic 22.5) — derived from connector_id prefix
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CapabilityRecord:
    capability_name: str  # "tool.execute.family.calendar.create"
    connector_id: str  # "family.calendar"
    invocation_mode: str  # 'read' | 'execute'
    action_name: str  # 'list' | 'search' | 'create' | 'update' | 'delete' | 'send'
    effect: str  # 'read' | 'write' | 'delete' | 'compute'
    resource_kind: str | None  # "calendar_event" — legacy; prefer family_id (Phase 2.6)
    domain_id: str = ""  # Phase 2.6 (Epic 22.6) — taxonomy domain
    family_id: str | None = None  # Phase 2.6 (Epic 22.6) — taxonomy resource family
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
    kind_id: str  # e.g. 'calendar.event', 'task.item'
    connector_id: str
    label: str
    schema: dict = field(default_factory=dict)
    verifier_affordances: list[str] = field(default_factory=list)
    created_at: str = ""


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


# ---------------------------------------------------------------------------
# LoadResult — returned by load_from_manifest_batch
# ---------------------------------------------------------------------------


@dataclass
class LoadResult:
    total_connectors: int
    total_capabilities: int
    admitted: int
    rejected: int
    errors: list[str] = field(default_factory=list)


@dataclass
class CapabilityRegistrationBatch:
    """Batch of capabilities to register together (used by load_from_manifest_batch)."""

    connector: ConnectorRecord
    capabilities: list[CapabilityRecord]
    resource_kinds: list[ResourceKindRecord] = field(default_factory=list)
    constitution: ConstitutionRecord | None = None


# ---------------------------------------------------------------------------
# Phase 2.6 — Taxonomy seed helpers
# ---------------------------------------------------------------------------

_DOMAINS_SEED: list[tuple[str, str, str]] = [
    ("family", "Family & Household", "Parenting, chores, calendar, shopping, meal planning"),
    ("finance", "Banking & Finance", "Accounts, transactions, budgets, investments, taxes"),
    ("health", "Health & Wellness", "Medical records, prescriptions, fitness, nutrition"),
    ("education", "Education & Learning", "Courses, assignments, grades, degrees"),
    ("home", "Smart Home & Living", "Devices, appliances, security, energy"),
    ("transport", "Transport & Travel", "Rides, deliveries, flights, hotels, vehicles"),
    ("food", "Food & Cooking", "Recipes, meal planning, groceries, restaurants"),
    ("fitness", "Fitness & Activity", "Workouts, tracking, goals, wearables"),
    ("entertainment", "Media & Entertainment", "Streaming, gaming, events, subscriptions"),
    ("productivity", "Work & Productivity", "Notes, documents, projects, calendars, email"),
    ("communication", "Messaging & Social", "Chat, calls, social media, announcements"),
    ("government", "Government & Civic", "Permits, benefits, taxes, voting"),
    ("legal", "Legal & Compliance", "Contracts, documents, filings"),
    ("utilities", "Utilities & Services", "Electricity, water, gas, internet, waste"),
    ("agriculture", "Agriculture & Farming", "Crops, livestock, equipment, weather"),
    ("automotive", "Automotive & Vehicles", "Cars, maintenance, registration, insurance"),
]


def _seed_domains(db: sqlite3.Connection) -> None:
    """Insert the 16 FamilyOS-governed domains (idempotent)."""
    db.executemany(
        "INSERT OR IGNORE INTO domains (domain_id, label, description) VALUES (?, ?, ?)",
        _DOMAINS_SEED,
    )


_RESOURCE_FAMILIES_SEED: list[tuple[str, str, str]] = [
    # ── Cross-domain families (shared across many domains) ──
    ("event", "Events", "Calendar events, appointments, meetings, and scheduled occurrences"),
    ("task", "Tasks", "To-do items, action items, homework, and completable work units"),
    ("reminder", "Reminders", "Time-based notification reminders and alerts"),
    ("item", "Items", "Purchasable or trackable items: groceries, supplies, products"),
    ("record", "Records", "General-purpose records, logs, entries, and filings"),
    ("contact", "Contacts", "People, profiles, relationships, and address book entries"),
    ("setting", "Settings", "Configuration, preferences, feature flags, and policy values"),
    ("metric", "Metrics", "Measurements, statistics, vital signs, scores, and KPIs"),
    ("subscription", "Subscriptions", "Recurring subscriptions, memberships, and service plans"),
    ("message", "Messages", "Chat messages, notifications, announcements, and communications"),
    ("order", "Orders", "Purchase orders, service requests, and fulfilment orders"),
    # ── Domain-specific families ──
    ("chore", "Chores", "Recurring household duties and responsibilities"),
    ("recipe", "Recipes", "Cooking recipes, meal plans, and preparation instructions"),
    ("account", "Accounts", "Financial accounts: checking, savings, credit, investment"),
    ("transaction", "Transactions", "Financial transactions, payments, deposits, and transfers"),
    ("budget", "Budgets", "Spending budgets, allocations, and financial plans"),
    ("investment", "Investments", "Investment holdings, portfolios, stocks, and funds"),
    ("loan", "Loans", "Loans, mortgages, debt instruments, and repayment schedules"),
    ("insurance", "Insurance", "Insurance policies, claims, coverage, and premiums"),
    ("tax", "Tax", "Tax records, filings, deductions, and returns"),
    ("prescription", "Prescriptions", "Medical prescriptions, medications, dosages, and refills"),
    ("immunization", "Immunizations", "Vaccination records, immunization schedules, and boosters"),
    ("lab_order", "Lab Orders", "Laboratory test orders, results, panels, and imaging"),
    ("vital", "Vital Signs", "Blood pressure, heart rate, temperature, weight, and biometrics"),
    ("allergy", "Allergies", "Allergy records, reactions, severity, and treatments"),
    ("condition", "Conditions", "Medical conditions, diagnoses, chronic issues, and symptoms"),
    ("course", "Courses", "Educational courses, classes, modules, and curricula"),
    ("assignment", "Assignments", "Homework, projects, papers, and graded submissions"),
    ("grade", "Grades", "Grades, scores, transcripts, and academic standing"),
    ("credential", "Credentials", "Degrees, certificates, licences, and qualifications"),
    ("device", "Devices", "Smart home devices, appliances, sensors, and IoT endpoints"),
    ("energy", "Energy", "Energy usage, electricity, gas, water, and utility consumption"),
    ("security", "Security", "Security systems, cameras, locks, alarms, and access control"),
    ("ride", "Rides", "Ride-share trips, taxi journeys, and chauffeur services"),
    ("delivery", "Deliveries", "Package deliveries, shipments, courier services, and tracking"),
    ("flight", "Flights", "Airline flights, itineraries, boarding, and reservations"),
    ("hotel", "Hotels", "Hotel bookings, accommodations, check-in, and reservations"),
    ("vehicle", "Vehicles", "Cars, vehicles, registration, service history, and maintenance"),
    ("workout", "Workouts", "Exercise routines, fitness sessions, training plans, and activities"),
    ("meal", "Meals", "Meals, dining, nutrition intake, and food logging"),
    ("playlist", "Playlists", "Media playlists, watchlists, queues, and collections"),
    ("game", "Games", "Games, gaming sessions, achievements, and progress"),
    ("permit", "Permits", "Government permits, licences, applications, and approvals"),
    ("benefit", "Benefits", "Government benefits, entitlements, social services, and aid"),
    ("payment", "Payments", "Payment methods, billing, invoices, and settlement"),
    ("invoice", "Invoices", "Invoices, bills, receipts, and statements"),
    ("policy", "Policies", "Policy documents, rules, terms, agreements, and contracts"),
    ("document", "Documents", "Files, documents, attachments, and digital assets"),
    (
        "certification",
        "Certifications",
        "Professional certifications, compliance, audits, and attestations",
    ),
    ("notification", "Notifications", "Push notifications, alerts, reminders, and status updates"),
    ("report", "Reports", "Analytics reports, summaries, dashboards, and exports"),
    ("reservation", "Reservations", "Table bookings, venue reservations, and appointment slots"),
    ("shipment", "Shipments", "Cargo, freight, shipping manifests, and logistics"),
    ("maintenance", "Maintenance", "Equipment maintenance, service schedules, repairs, and upkeep"),
    ("weather", "Weather", "Weather forecasts, conditions, alerts, and climate data"),
    ("pet", "Pets", "Pet records, veterinary visits, feeding schedules, and care"),
    ("plant", "Plants", "Plants, crops, garden beds, watering, and harvests"),
]


def _seed_resource_families(db: sqlite3.Connection) -> None:
    """Insert 56 FamilyOS-governed resource families (idempotent)."""
    db.executemany(
        "INSERT OR IGNORE INTO resource_families (family_id, label, description) VALUES (?, ?, ?)",
        _RESOURCE_FAMILIES_SEED,
    )


# (domain_id, family_id) pairs — 130+ mappings across all 16 domains.
_DOMAIN_RESOURCE_FAMILIES_SEED: list[tuple[str, str]] = [
    # family — parenting, chores, calendar, shopping, meal planning
    ("family", "event"),
    ("family", "task"),
    ("family", "reminder"),
    ("family", "chore"),
    ("family", "item"),
    ("family", "recipe"),
    ("family", "contact"),
    ("family", "setting"),
    ("family", "meal"),
    ("family", "record"),
    ("family", "subscription"),
    ("family", "message"),
    ("family", "pet"),
    ("family", "notification"),
    # finance — accounts, transactions, budgets, investments, taxes
    ("finance", "account"),
    ("finance", "transaction"),
    ("finance", "budget"),
    ("finance", "investment"),
    ("finance", "loan"),
    ("finance", "insurance"),
    ("finance", "tax"),
    ("finance", "record"),
    ("finance", "contact"),
    ("finance", "metric"),
    ("finance", "subscription"),
    ("finance", "payment"),
    ("finance", "invoice"),
    ("finance", "report"),
    ("finance", "policy"),
    # health — medical records, prescriptions, fitness, nutrition
    ("health", "prescription"),
    ("health", "immunization"),
    ("health", "lab_order"),
    ("health", "vital"),
    ("health", "allergy"),
    ("health", "condition"),
    ("health", "event"),
    ("health", "contact"),
    ("health", "record"),
    ("health", "metric"),
    ("health", "insurance"),
    ("health", "workout"),
    ("health", "meal"),
    ("health", "notification"),
    ("health", "report"),
    ("health", "document"),
    ("health", "certification"),
    # education — courses, assignments, grades, degrees
    ("education", "course"),
    ("education", "assignment"),
    ("education", "grade"),
    ("education", "credential"),
    ("education", "event"),
    ("education", "task"),
    ("education", "record"),
    ("education", "contact"),
    ("education", "subscription"),
    ("education", "document"),
    ("education", "certification"),
    ("education", "report"),
    # home — devices, appliances, security, energy
    ("home", "device"),
    ("home", "energy"),
    ("home", "security"),
    ("home", "setting"),
    ("home", "subscription"),
    ("home", "record"),
    ("home", "maintenance"),
    ("home", "notification"),
    ("home", "metric"),
    ("home", "weather"),
    # transport — rides, deliveries, flights, hotels, vehicles
    ("transport", "ride"),
    ("transport", "delivery"),
    ("transport", "flight"),
    ("transport", "hotel"),
    ("transport", "vehicle"),
    ("transport", "order"),
    ("transport", "subscription"),
    ("transport", "record"),
    ("transport", "reservation"),
    ("transport", "shipment"),
    ("transport", "maintenance"),
    ("transport", "notification"),
    # food — recipes, meal planning, groceries, restaurants
    ("food", "recipe"),
    ("food", "item"),
    ("food", "meal"),
    ("food", "subscription"),
    ("food", "order"),
    ("food", "reservation"),
    ("food", "record"),
    # fitness — workouts, tracking, goals, wearables
    ("fitness", "workout"),
    ("fitness", "metric"),
    ("fitness", "device"),
    ("fitness", "subscription"),
    ("fitness", "event"),
    ("fitness", "record"),
    ("fitness", "report"),
    ("fitness", "notification"),
    # entertainment — streaming, gaming, events, subscriptions
    ("entertainment", "subscription"),
    ("entertainment", "playlist"),
    ("entertainment", "game"),
    ("entertainment", "event"),
    ("entertainment", "order"),
    ("entertainment", "item"),
    ("entertainment", "record"),
    # productivity — notes, documents, projects, calendars, email
    ("productivity", "task"),
    ("productivity", "event"),
    ("productivity", "document"),
    ("productivity", "record"),
    ("productivity", "contact"),
    ("productivity", "setting"),
    ("productivity", "subscription"),
    ("productivity", "report"),
    ("productivity", "notification"),
    ("productivity", "message"),
    # communication — chat, calls, social media, announcements
    ("communication", "message"),
    ("communication", "contact"),
    ("communication", "notification"),
    ("communication", "subscription"),
    ("communication", "event"),
    ("communication", "record"),
    # government — permits, benefits, taxes, voting
    ("government", "permit"),
    ("government", "benefit"),
    ("government", "tax"),
    ("government", "record"),
    ("government", "document"),
    ("government", "certification"),
    ("government", "notification"),
    # legal — contracts, documents, filings
    ("legal", "document"),
    ("legal", "policy"),
    ("legal", "record"),
    ("legal", "contact"),
    ("legal", "certification"),
    ("legal", "notification"),
    ("legal", "subscription"),
    # utilities — electricity, water, gas, internet, waste
    ("utilities", "energy"),
    ("utilities", "subscription"),
    ("utilities", "record"),
    ("utilities", "metric"),
    ("utilities", "maintenance"),
    ("utilities", "notification"),
    ("utilities", "invoice"),
    ("utilities", "payment"),
    # agriculture — crops, livestock, equipment, weather
    ("agriculture", "plant"),
    ("agriculture", "weather"),
    ("agriculture", "maintenance"),
    ("agriculture", "record"),
    ("agriculture", "metric"),
    ("agriculture", "device"),
    ("agriculture", "shipment"),
    ("agriculture", "report"),
    ("agriculture", "pet"),
    # automotive — cars, maintenance, registration, insurance
    ("automotive", "vehicle"),
    ("automotive", "maintenance"),
    ("automotive", "insurance"),
    ("automotive", "record"),
    ("automotive", "document"),
    ("automotive", "certification"),
    ("automotive", "notification"),
    ("automotive", "subscription"),
]


def _seed_domain_resource_families(db: sqlite3.Connection) -> None:
    """Insert 130+ domain→family mappings (idempotent)."""
    db.executemany(
        "INSERT OR IGNORE INTO domain_resource_families (domain_id, family_id) VALUES (?, ?)",
        _DOMAIN_RESOURCE_FAMILIES_SEED,
    )


def _ensure_fts5(db: sqlite3.Connection, cap_cols: set[str]) -> None:
    """Create or rebuild capabilities_fts with taxonomy columns.

    If the FTS5 table doesn't exist, create it with the Phase 2.6 column set
    (including domain_id + family_id).  If it exists but was created before
    Phase 2.6 (only 4 columns), drop and recreate so BM25 can index the new
    taxonomy columns.
    """
    # Check existing FTS5 column count
    fts_cols: set[str] = set()
    try:
        fts_info = db.execute("PRAGMA table_info(capabilities_fts)").fetchall()
        fts_cols = {r[1] for r in fts_info}
    except Exception:
        pass  # Table doesn't exist — will be created below

    needs_rebuild = bool(fts_cols) and (
        "domain_id" not in fts_cols or "family_id" not in fts_cols or "action_name" not in fts_cols
    )
    if needs_rebuild:
        db.execute("DROP TABLE IF EXISTS capabilities_fts")

    if not fts_cols or needs_rebuild:
        db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts USING fts5(
                capability_name, action_name, description, family_id, connector_id, domain_id,
                content='capabilities', content_rowid='rowid'
            )
            """)
        # Trigger initial index population
        db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")


def _ensure_connectors_fts5(db: sqlite3.Connection) -> None:
    """Create or rebuild connectors_fts for connector-level search.

    Standalone FTS5 table (not content-sync) — rows are INSERTed
    explicitly via upsert_connector_fts_text().  This avoids ALTER
    TABLE on the connectors table.
    """
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS connectors_fts USING fts5(
            connector_id, label, description, search_text
        )
    """)


# ---------------------------------------------------------------------------
# GlobalProjectionStore
# ---------------------------------------------------------------------------


class GlobalProjectionStore:
    """Shared SQLite store for all capability contracts, connectors, graph ontology.

    Thread safety: SQLite WAL mode + check_same_thread=False.
    Writes are serialised by CapabilityRegistryAPI — no additional mutex needed.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        # ── MiniLM embedding index (lazy-built on first search_connectors call, RES-003-core) ──
        self._embedding_model: Any = None
        self._embedding_matrix: Any = None  # numpy array (n_connectors, 384)
        self._embedding_connector_ids: list[str] = []
        self._embedding_labels: list[str] = []  # human-readable connector label
        self._embedding_descriptions: list[str] = []  # connector description/search_text
        self._embedding_index_built: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the database in WAL mode and ensure the schema exists."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()
        self._conn.commit()

    def warmup_embedding_index(self) -> None:
        """Eagerly build the MiniLM-L6 embedding index during startup.

        By default the embedding model is lazy-loaded on the first
        ``search_connectors`` call (first ``resolve_situation`` tool use),
        which adds ~30s latency to the first user request.  Call this
        during kernel startup to pay that cost upfront.
        """
        self._ensure_embedding_index()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("GlobalProjectionStore is not open")
        return self._conn

    # ── Issue 1.2 — SQL Schema ──────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create all tables and indexes if they do not exist.

        10 data tables + 1 FTS5 virtual table + 1 index.
        """
        db = self._db

        # ── Phase 2.6 taxonomy tables (created before connectors so FK refs resolve) ──

        # 0.1 Domains — FamilyOS-governed top-level taxonomy
        db.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                domain_id    TEXT PRIMARY KEY,
                label        TEXT NOT NULL,
                description  TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """)
        _seed_domains(db)

        # 0.2 Resource families — cross-domain + domain-specific taxonomy terms
        db.execute("""
            CREATE TABLE IF NOT EXISTS resource_families (
                family_id    TEXT PRIMARY KEY,
                label        TEXT NOT NULL,
                description  TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """)
        _seed_resource_families(db)

        # 0.3 Domain ↔ resource family mapping
        db.execute("""
            CREATE TABLE IF NOT EXISTS domain_resource_families (
                domain_id    TEXT NOT NULL REFERENCES domains(domain_id),
                family_id    TEXT NOT NULL REFERENCES resource_families(family_id),
                PRIMARY KEY (domain_id, family_id)
            )
            """)
        _seed_domain_resource_families(db)

        # 0.4 Connector ↔ resource family (populated at bootstrap by register_definition_to_store)
        db.execute("""
            CREATE TABLE IF NOT EXISTS connector_resource_families (
                connector_id TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
                family_id    TEXT NOT NULL REFERENCES resource_families(family_id),
                is_primary   INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (connector_id, family_id)
            )
            """)

        # 1. Connectors
        db.execute("""
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
                guide_cards_json TEXT NOT NULL DEFAULT '[]',
                domain_id       TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """)

        # Migration: add guide_cards_json to connectors for databases created
        # before Phase 1.1 (Epic 9.5).  ALTER is a no-op when the column is
        # already present (fresh databases get it from the CREATE TABLE above).
        connector_cols = {r[1] for r in db.execute("PRAGMA table_info(connectors)").fetchall()}
        if "guide_cards_json" not in connector_cols:
            db.execute(
                "ALTER TABLE connectors ADD COLUMN " "guide_cards_json TEXT NOT NULL DEFAULT '[]'"
            )

        # Migration: add domain_id to connectors (Phase 2.6, Epic 22.5).
        # Populated from connector_id prefix for existing rows.
        if "domain_id" not in connector_cols:
            db.execute("ALTER TABLE connectors ADD COLUMN domain_id TEXT NOT NULL DEFAULT ''")
            db.execute(
                "UPDATE connectors SET domain_id = "
                "substr(connector_id, 1, instr(connector_id, '.') - 1) "
                "WHERE domain_id = '' AND instr(connector_id, '.') > 0"
            )

        # 2. Capabilities
        db.execute("""
            CREATE TABLE IF NOT EXISTS capabilities (
                capability_name TEXT PRIMARY KEY,
                connector_id    TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
                invocation_mode TEXT NOT NULL CHECK(invocation_mode IN ('read','execute')),
                action_name     TEXT NOT NULL,
                effect          TEXT NOT NULL CHECK(effect IN ('read','write','delete','compute')),
                resource_kind   TEXT,
                domain_id       TEXT NOT NULL DEFAULT '',
                family_id       TEXT,
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
            )
            """)

        # Migration: add domain_id + family_id to capabilities (Phase 2.6, Epic 22.6).
        # resource_kind stays — SQLite cannot DROP COLUMN in older versions.
        cap_cols = {r[1] for r in db.execute("PRAGMA table_info(capabilities)").fetchall()}
        if "domain_id" not in cap_cols:
            db.execute("ALTER TABLE capabilities ADD COLUMN domain_id TEXT NOT NULL DEFAULT ''")
        if "family_id" not in cap_cols:
            db.execute("ALTER TABLE capabilities ADD COLUMN family_id TEXT")
        if "domain_id" not in cap_cols or "family_id" not in cap_cols:
            db.execute(
                "UPDATE capabilities SET "
                "domain_id = COALESCE("
                "  (SELECT c.domain_id FROM connectors c "
                "   WHERE c.connector_id = capabilities.connector_id), ''"
                "), "
                "family_id = resource_kind "
                "WHERE domain_id = ''"
            )

        # Index: include domain_id + family_id alongside resource_kind for
        # efficient typed lookups.  resource_kind stays in the index for
        # backward-compatible queries.
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_capability_lookup
                ON capabilities(family_id, resource_kind, invocation_mode, effect,
                                domain_id, connector_id, record_type, safety_band_min)
            """)

        # 3. FTS5 full-text search — rebuild with taxonomy columns if needed
        _ensure_fts5(db, cap_cols)

        # 3b. Connector-level FTS5 for connector-first search (RES-004, 2026-06-16)
        # Indexes connector label + description + aggregated capability names.
        # Used by search_connectors() in Phase 3 (RES-007a ConnectorResolver).
        _ensure_connectors_fts5(db)

        # 4. Resource kinds
        db.execute("""
            CREATE TABLE IF NOT EXISTS resource_kinds (
                kind_id         TEXT PRIMARY KEY,
                connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
                label           TEXT NOT NULL,
                schema_json     TEXT NOT NULL DEFAULT '{}',
                verifier_affordances_json TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL
            )
            """)

        # 5. Connector constitutions (per-connector, not per-operation)
        db.execute("""
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
                -- NEW: POC v2 teaching surface fields (RES-000b, 2026-06-16)
                how_to_sequence_json        TEXT NOT NULL DEFAULT '[]',
                what_to_verify_json         TEXT NOT NULL DEFAULT '[]',
                when_to_ask_human_json      TEXT NOT NULL DEFAULT '[]',
                companion_connectors_json   TEXT NOT NULL DEFAULT '[]',
                conflict_rules_json         TEXT NOT NULL DEFAULT '[]',
                precondition_summary        TEXT,
                companion_resource_summary  TEXT,
                hil_trigger_summary         TEXT,
                degradation_policy          TEXT
            )
            """)

        # 5b. Connector backend registry (RES-000c, 2026-06-16)
        # Registers which backends a connector CAN support.
        # LPS connected_resources records which backends ARE connected for a session.
        # Intersection = live enum for dynamic tool schema injection (RES-011b).
        db.execute("""
            CREATE TABLE IF NOT EXISTS connector_backends (
                connector_id TEXT NOT NULL,
                backend_id TEXT NOT NULL,
                backend_label TEXT NOT NULL DEFAULT '',
                schema_version TEXT NOT NULL DEFAULT '1.0.0',
                registered_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (connector_id, backend_id)
            )
            """)

        # 6–11. Graph ontology tables
        db.execute("""
            CREATE TABLE IF NOT EXISTS concept_aliases (
                alias TEXT NOT NULL, canonical_concept TEXT NOT NULL, domain TEXT,
                weight REAL DEFAULT 1.0, generic INTEGER DEFAULT 0, source TEXT DEFAULT 'catalog',
                PRIMARY KEY(alias, canonical_concept, domain)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS concept_resource_edges (
                concept TEXT NOT NULL, resource_family TEXT NOT NULL, domain TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                PRIMARY KEY(concept, resource_family, domain)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS resource_connector_edges (
                domain TEXT NOT NULL, resource_family TEXT NOT NULL, connector_id TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                role TEXT NOT NULL DEFAULT 'primary'
                    CHECK(role IN ('primary','companion','verifier','prerequisite')),
                PRIMARY KEY(domain, resource_family, connector_id)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS operation_equivalences (
                canonical_operation TEXT NOT NULL,
                equivalent_operation TEXT NOT NULL,
                resource_family TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(canonical_operation, equivalent_operation, resource_family, domain)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS operation_aliases (
                alias TEXT NOT NULL, operation_family TEXT NOT NULL, effect TEXT NOT NULL,
                weight REAL DEFAULT 1.0, generic INTEGER DEFAULT 1,
                PRIMARY KEY(alias, operation_family)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS capability_type_index (
                capability_name TEXT NOT NULL, connector_id TEXT NOT NULL, domain TEXT NOT NULL,
                resource_family TEXT NOT NULL, operation_family TEXT NOT NULL, effect TEXT NOT NULL,
                side_effect_class TEXT, risk_class TEXT,
                PRIMARY KEY(capability_name, resource_family, operation_family, effect)
            )
            """)

    # ── Issue 1.3 — Connector CRUD ──────────────────────────────────────

    def upsert_connector(self, connector: ConnectorRecord) -> None:
        self._db.execute(
            """
            INSERT INTO connectors (connector_id, label, connector_type, provider_type, version,
                admission_verdict, registration_type, constitution_json, policy_json,
                resource_kinds_json, guide_cards_json, domain_id, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(connector_id) DO UPDATE SET
                label=excluded.label, connector_type=excluded.connector_type,
                provider_type=excluded.provider_type, version=excluded.version,
                admission_verdict=excluded.admission_verdict,
                registration_type=excluded.registration_type,
                constitution_json=excluded.constitution_json,
                policy_json=excluded.policy_json,
                resource_kinds_json=excluded.resource_kinds_json,
                guide_cards_json=excluded.guide_cards_json,
                domain_id=excluded.domain_id,
                updated_at=excluded.updated_at
            """,
            (
                connector.connector_id,
                connector.label,
                connector.connector_type,
                connector.provider_type,
                connector.version,
                connector.admission_verdict,
                connector.registration_type,
                json.dumps(connector.constitution, sort_keys=True),
                json.dumps(connector.policy_declarations, sort_keys=True),
                json.dumps(connector.resource_kinds, sort_keys=True),
                json.dumps(connector.guide_cards, sort_keys=True),
                connector.domain_id,
                connector.created_at,
                connector.updated_at,
            ),
        )
        self._db.commit()

    def get_connector(self, connector_id: str) -> ConnectorRecord | None:
        row = self._db.execute(
            "SELECT * FROM connectors WHERE connector_id = ?", (connector_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_connector(row)

    def list_connectors(self, *, connector_type: str | None = None) -> list[ConnectorRecord]:
        if connector_type is not None:
            rows = self._db.execute(
                "SELECT * FROM connectors WHERE connector_type = ?", (connector_type,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM connectors").fetchall()
        return [self._row_to_connector(r) for r in rows]

    def delete_connector(self, connector_id: str) -> None:
        self._db.execute("DELETE FROM connectors WHERE connector_id = ?", (connector_id,))
        self._db.commit()

    def connector_exists(self, connector_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM connectors WHERE connector_id = ?", (connector_id,)
        ).fetchone()
        return row is not None

    # ── Capability CRUD ─────────────────────────────────────────────────

    def upsert_capability(self, capability: CapabilityRecord) -> None:
        # Auto-populate domain_id from connector_id prefix if not set
        # (e.g. "family.calendar" → "family").  This ensures
        # search_capabilities_by_domain works correctly for freshly
        # inserted capabilities.  (RES-003-core bugfix, 2026-06-17)
        domain_id = capability.domain_id
        if not domain_id and capability.connector_id:
            domain_id = capability.connector_id.split(".")[0]
        family_id = capability.family_id
        self._db.execute(
            """
            INSERT INTO capabilities (capability_name, connector_id, invocation_mode,
                action_name, effect, resource_kind, domain_id, family_id,
                description, required_inputs_json,
                optional_inputs_json, output_schema_ref, safety_band_min, risk_class,
                idempotency, compensation_capability, record_type, created_at,
                contract_json, synthetic)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(capability_name) DO UPDATE SET
                connector_id=excluded.connector_id, invocation_mode=excluded.invocation_mode,
                action_name=excluded.action_name, effect=excluded.effect,
                resource_kind=excluded.resource_kind,
                domain_id=excluded.domain_id, family_id=excluded.family_id,
                description=excluded.description,
                required_inputs_json=excluded.required_inputs_json,
                optional_inputs_json=excluded.optional_inputs_json,
                output_schema_ref=excluded.output_schema_ref,
                safety_band_min=excluded.safety_band_min, risk_class=excluded.risk_class,
                idempotency=excluded.idempotency,
                compensation_capability=excluded.compensation_capability,
                record_type=excluded.record_type, created_at=excluded.created_at,
                contract_json=excluded.contract_json, synthetic=excluded.synthetic
            """,
            (
                capability.capability_name,
                capability.connector_id,
                capability.invocation_mode,
                capability.action_name,
                capability.effect,
                capability.resource_kind,
                domain_id,
                family_id,
                capability.description,
                json.dumps(capability.required_inputs, sort_keys=True),
                json.dumps(capability.optional_inputs, sort_keys=True),
                capability.output_schema_ref,
                capability.safety_band_min,
                capability.risk_class,
                capability.idempotency,
                capability.compensation_capability,
                capability.record_type,
                capability.created_at,
                json.dumps(capability.contract_json, sort_keys=True),
                1 if capability.synthetic else 0,
            ),
        )
        # FTS5 content-sync: single upsert → rebuild
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")
        self._db.commit()

    def bulk_upsert_capabilities(
        self,
        capabilities: list[CapabilityRecord],
        *,
        chunk_size: int = 25_000,
    ) -> None:
        """Bulk-insert capabilities with chunked FTS5 content-sync.

        Emits 'delete-all' first, chunk-inserts at *chunk_size* rows,
        then calls ``rebuild_fts_index()`` once at the end.
        """
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('delete-all')")
        for i in range(0, len(capabilities), chunk_size):
            chunk = capabilities[i : i + chunk_size]
            self._db.executemany(
                """
                INSERT OR REPLACE INTO capabilities (capability_name, connector_id,
                    invocation_mode, action_name, effect, resource_kind, domain_id, family_id,
                    description,
                    required_inputs_json, optional_inputs_json, output_schema_ref,
                    safety_band_min, risk_class, idempotency, compensation_capability,
                    record_type, created_at, contract_json, synthetic)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        c.capability_name,
                        c.connector_id,
                        c.invocation_mode,
                        c.action_name,
                        c.effect,
                        c.resource_kind,
                        c.domain_id,
                        c.family_id,
                        c.description,
                        json.dumps(c.required_inputs, sort_keys=True),
                        json.dumps(c.optional_inputs, sort_keys=True),
                        c.output_schema_ref,
                        c.safety_band_min,
                        c.risk_class,
                        c.idempotency,
                        c.compensation_capability,
                        c.record_type,
                        c.created_at,
                        json.dumps(c.contract_json, sort_keys=True),
                        1 if c.synthetic else 0,
                    )
                    for c in chunk
                ],
            )
        self.rebuild_fts_index()

    def get_capability(self, capability_name: str) -> CapabilityRecord | None:
        row = self._db.execute(
            "SELECT * FROM capabilities WHERE capability_name = ?",
            (capability_name,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_capability(row)

    def get_capabilities_by_connector(self, connector_id: str) -> list[CapabilityRecord]:
        rows = self._db.execute(
            "SELECT * FROM capabilities WHERE connector_id = ?", (connector_id,)
        ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    def delete_capability(self, capability_name: str) -> None:
        self._db.execute("DELETE FROM capabilities WHERE capability_name = ?", (capability_name,))
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")
        self._db.commit()

    def capability_exists(self, capability_name: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM capabilities WHERE capability_name = ?",
            (capability_name,),
        ).fetchone()
        return row is not None

    def count_capabilities(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM capabilities").fetchone()
        return int(row[0]) if row else 0

    def list_all_capabilities(self) -> list[CapabilityRecord]:
        """Return every capability in the store — used by fallback_mode."""
        rows = self._db.execute("SELECT * FROM capabilities").fetchall()
        return [self._row_to_capability(r) for r in rows]

    # ── FTS5 Search ─────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """FTS5 query with OR semantics + prefix matching.

        FTS5 default is implicit AND — too strict.  We convert to OR with
        prefix wildcards.  Tokens shorter than 2 chars are dropped (FTS5
        minimum token length).  Single-token queries use simple prefix.

          "add eggs to shopping list" → "add* OR eggs* OR shopping* OR list*"
        """
        if not query:
            return ""
        unsafe = set("^~!@#$%&/()=?`'{}[]\\|<>.,;:\n\r\t")
        cleaned = "".join(c if c not in unsafe else " " for c in query)
        tokens = [t for t in cleaned.split() if len(t) >= 2]
        if not tokens:
            return ""
        if len(tokens) == 1:
            return f'"{tokens[0]}"*'
        return " OR ".join(f'"{t}"*' for t in tokens)

    def search_capabilities(
        self,
        query: str,
        *,
        top_k: int = 20,
        connector_ids: list[str] | None = None,
    ) -> list[CapabilityRecord]:
        query = self._sanitize_fts_query(query)
        if not query:
            return []
        if connector_ids:
            placeholders = ",".join("?" for _ in connector_ids)
            rows = self._db.execute(
                f"""
                SELECT c.* FROM capabilities c
                JOIN capabilities_fts fts ON c.rowid = fts.rowid
                WHERE capabilities_fts MATCH ?
                  AND c.connector_id IN ({placeholders})
                ORDER BY rank
                LIMIT ?
                """,
                [query] + connector_ids + [top_k],
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT c.* FROM capabilities c
                JOIN capabilities_fts fts ON c.rowid = fts.rowid
                WHERE capabilities_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    def search_capabilities_by_domain(
        self,
        query: str,
        domains: list[str],
        *,
        top_k: int = 20,
    ) -> list[CapabilityRecord]:
        query = self._sanitize_fts_query(query)
        if not query or not domains:
            return self.search_capabilities(query, top_k=top_k)
        # Use domain_id column (Phase 2.6) instead of connector_id LIKE prefix hack
        placeholders = ", ".join("?" for _ in domains)
        rows = self._db.execute(
            f"""
            SELECT c.* FROM capabilities c
            JOIN capabilities_fts fts ON c.rowid = fts.rowid
            WHERE capabilities_fts MATCH ?
              AND c.domain_id IN ({placeholders})
            ORDER BY rank
            LIMIT ?
            """,
            [query] + domains + [top_k],
        ).fetchall()
        # Auto-retry without domain filter when domain-scoped search returns
        # zero results.  This handles hallucinated domains (e.g. "healthcare",
        # "xyzzy") where no capabilities exist.  FTS5 OR semantics already
        # found matching text; the domain filter incorrectly killed results.
        if not rows:
            rows = self._db.execute(
                """
                SELECT c.* FROM capabilities c
                JOIN capabilities_fts fts ON c.rowid = fts.rowid
                WHERE capabilities_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    def rebuild_fts_index(self) -> None:
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")
        self._db.commit()

    # ── Connector-level FTS (Epic 1.1, RES-004/005, 2026-06-16) ──────

    def upsert_connector_fts_text(
        self, connector_id: str, label: str, description: str, search_text: str
    ) -> None:
        """Insert or update a connector's FTS row.

        Called during manifest admission (RES-004) and family bootstrap
        (RES-005).  The FTS5 table is standalone — no content-sync triggers.
        """
        # Delete old row if exists (FTS5 has no UPSERT)
        self._db.execute(
            "DELETE FROM connectors_fts WHERE connector_id = ?",
            (connector_id,),
        )
        self._db.execute(
            "INSERT INTO connectors_fts(connector_id, label, description, search_text) "
            "VALUES (?, ?, ?, ?)",
            (connector_id, label, description, search_text),
        )
        self._db.commit()
        # Invalidate embedding index so next search_connectors() rebuilds
        self._embedding_index_built = False

    # ── MiniLM dense retrieval (RES-003-core, 2026-06-17) ───────────────

    def _ensure_embedding_index(self) -> None:
        """Build or rebuild the MiniLM-L6 embedding index from connectors.

        Reads every connector row, builds a search document from label +
        description, encodes with MiniLM-L6 (normalized), and stores the
        embedding matrix for cosine-similarity search.

        Idempotent — subsequent calls are no-ops unless the connector
        count changes (new admission / bootstrap).
        """
        import numpy as np

        rows = self._db.execute(
            "SELECT c.connector_id, c.label, c.domain_id,"
            "  COALESCE(f.search_text, c.label) AS search_text "
            "FROM connectors c "
            "LEFT JOIN connectors_fts f ON c.connector_id = f.connector_id"
        ).fetchall()

        if not rows:
            self._embedding_connector_ids = []
            self._embedding_labels = []
            self._embedding_descriptions = []
            self._embedding_matrix = np.empty((0, 384), dtype=np.float32)
            self._embedding_index_built = True
            return

        current_ids = [r[0] for r in rows]
        current_labels = [r[1] or r[0] for r in rows]
        current_descs = [r[3] or "" for r in rows]
        if (
            self._embedding_index_built
            and self._embedding_connector_ids == current_ids
            and self._embedding_matrix.shape[0] == len(current_ids)
        ):
            return  # already up to date

        from sentence_transformers import SentenceTransformer

        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        # Build document text for embedding: label only (short, high-signal).
        # The full FTS search_text is too long for bi-encoder pooling —
        # a 15-word query gets drowned in 500+ words of aggregated text,
        # producing near-random cosine similarity.
        # The search_text is still returned as "description" in results so
        # the LLM can read it after ranking.
        texts: list[str] = current_labels

        embeddings = self._embedding_model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        self._embedding_matrix = np.asarray(embeddings, dtype=np.float32)
        self._embedding_connector_ids = current_ids
        self._embedding_labels = current_labels
        self._embedding_descriptions = current_descs
        self._embedding_index_built = True

        logger.info(
            "Embedding index built: %d connectors, shape=%s",
            len(current_ids),
            self._embedding_matrix.shape,
        )

    def search_connectors(
        self,
        action_text: str,
        *,
        top_k: int = 5,
        active_os_domains: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search connectors by MiniLM-L6 cosine similarity.

        Args:
            action_text: Raw user utterance (no LLM pre-processing).
            top_k: Number of results to return.
            active_os_domains: If provided, only return connectors whose
                ``domain_id`` is in this list (active-OS gating).

        Returns:
            List of dicts with keys: ``connector_id``, ``label``,
            ``domain_id``, ``score`` (cosine similarity, 0.0–1.0).
            Best match first.
        """
        import numpy as np

        self._ensure_embedding_index()

        if self._embedding_matrix.shape[0] == 0:
            return []

        query_vec = self._embedding_model.encode(
            [action_text], normalize_embeddings=True, show_progress_bar=False
        )
        scores = np.dot(self._embedding_matrix, query_vec.T).flatten()

        # Collect (idx, score) pairs, optionally gated by active_os_domains
        results: list[dict[str, Any]] = []
        domain_filter = set(active_os_domains) if active_os_domains else None

        for i, cid in enumerate(self._embedding_connector_ids):
            score = float(scores[i])
            if score <= 0.0:
                continue
            # Derive domain from connector_id prefix (e.g. "family.shopping" → "family")
            domain = cid.split(".")[0] if "." in cid else ""
            if domain_filter is not None and domain not in domain_filter:
                continue
            results.append(
                {
                    "connector_id": cid,
                    "label": self._embedding_labels[i] if i < len(self._embedding_labels) else cid,
                    "description": (
                        self._embedding_descriptions[i]
                        if i < len(self._embedding_descriptions)
                        else ""
                    ),
                    "domain_id": domain,
                    "score": round(score, 4),
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def invalidate_embedding_index(self) -> None:
        """Force rebuild of the embedding index on next search_connectors call.

        Call after manifest admission or family bootstrap adds/removes connectors.
        """
        self._embedding_index_built = False

    # ── Phase 2.6 — Taxonomy query methods ───────────────────────────────

    def get_domains(self) -> list[str]:
        """All registered domain IDs, alphabetical."""
        rows = self._db.execute("SELECT domain_id FROM domains ORDER BY domain_id").fetchall()
        return [r[0] for r in rows]

    def get_resource_families_for_domain(self, domain_id: str) -> list[dict[str, str]]:
        """Returns [{family_id, label, description}] for families valid in *domain_id*.

        JOINs resource_families ↔ domain_resource_families.
        """
        rows = self._db.execute(
            """SELECT rf.family_id, rf.label, rf.description
               FROM resource_families rf
               JOIN domain_resource_families drf ON rf.family_id = drf.family_id
               WHERE drf.domain_id = ?
               ORDER BY rf.family_id""",
            (domain_id,),
        ).fetchall()
        return [{"family_id": r[0], "label": r[1], "description": r[2]} for r in rows]

    def get_connector_resource_families(self, connector_id: str) -> list[str]:
        """Returns family_id list for a connector from connector_resource_families."""
        rows = self._db.execute(
            "SELECT family_id FROM connector_resource_families WHERE connector_id = ? ORDER BY family_id",
            (connector_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def find_capabilities(
        self,
        *,
        resource_kind: str,
        invocation_mode: str,
        effect: str,
        connector_id: str | None = None,
        safety_band: str = "RED",
        record_type: str | None = None,
    ) -> list[CapabilityRecord]:
        """Structured capability lookup backed by ``idx_capability_lookup``.

        Returns capabilities matching ``resource_kind`` + ``invocation_mode`` +
        ``effect`` (and optionally ``connector_id`` / ``record_type``) whose
        ``safety_band_min`` is at or below ``safety_band`` (the actor's maximum
        band).  ``safety_band='RED'`` admits every band.

        This is the exact-match (Pass 2) query for ``CapabilityBinderService``.
        """
        rank = {"GREEN": 1, "AMBER": 2, "RED": 3}
        max_rank = rank.get(safety_band, 3)
        allowed_bands = [b for b, r in rank.items() if r <= max_rank]
        band_placeholders = ",".join("?" for _ in allowed_bands)

        sql = [
            "SELECT * FROM capabilities",
            "WHERE resource_kind = ? AND invocation_mode = ? AND effect = ?",
            f"AND safety_band_min IN ({band_placeholders})",
        ]
        params: list[Any] = [resource_kind, invocation_mode, effect, *allowed_bands]
        if connector_id is not None:
            sql.append("AND connector_id = ?")
            params.append(connector_id)
        if record_type is not None:
            sql.append("AND record_type = ?")
            params.append(record_type)

        rows = self._db.execute(" ".join(sql), params).fetchall()
        return [self._row_to_capability(r) for r in rows]

    # ── Resource Kinds ──────────────────────────────────────────────────

    def upsert_resource_kind(self, kind: ResourceKindRecord) -> None:
        self._db.execute(
            """
            INSERT INTO resource_kinds (kind_id, connector_id, label, schema_json,
                verifier_affordances_json, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(kind_id) DO UPDATE SET
                connector_id=excluded.connector_id, label=excluded.label,
                schema_json=excluded.schema_json,
                verifier_affordances_json=excluded.verifier_affordances_json
            """,
            (
                kind.kind_id,
                kind.connector_id,
                kind.label,
                json.dumps(kind.schema, sort_keys=True),
                json.dumps(kind.verifier_affordances, sort_keys=True),
                kind.created_at,
            ),
        )
        self._db.commit()

    def get_resource_kinds_by_connector(self, connector_id: str) -> list[ResourceKindRecord]:
        rows = self._db.execute(
            "SELECT * FROM resource_kinds WHERE connector_id = ?", (connector_id,)
        ).fetchall()
        return [self._row_to_resource_kind(r) for r in rows]

    def get_resource_kind(self, kind_id: str) -> ResourceKindRecord | None:
        row = self._db.execute(
            "SELECT * FROM resource_kinds WHERE kind_id = ?", (kind_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_resource_kind(row)

    # ── Constitutions ───────────────────────────────────────────────────

    def upsert_constitution(self, constitution: ConstitutionRecord) -> None:
        self._db.execute(
            """
            INSERT INTO connector_constitutions (connector_id, constitution_id,
                schema_version, authored_by, authored_at, last_proven_at,
                execution_phases_json, prerequisite_reads_json,
                conflict_analysis_rules_json, hil_gates_json,
                mutation_sequencing_json, verification_requirements_json,
                companion_resource_roles_json, precondition_summary,
                companion_resource_summary, hil_trigger_summary, degradation_policy)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(connector_id) DO UPDATE SET
                constitution_id=excluded.constitution_id,
                schema_version=excluded.schema_version,
                authored_by=excluded.authored_by,
                authored_at=excluded.authored_at,
                last_proven_at=excluded.last_proven_at,
                execution_phases_json=excluded.execution_phases_json,
                prerequisite_reads_json=excluded.prerequisite_reads_json,
                conflict_analysis_rules_json=excluded.conflict_analysis_rules_json,
                hil_gates_json=excluded.hil_gates_json,
                mutation_sequencing_json=excluded.mutation_sequencing_json,
                verification_requirements_json=excluded.verification_requirements_json,
                companion_resource_roles_json=excluded.companion_resource_roles_json,
                precondition_summary=excluded.precondition_summary,
                companion_resource_summary=excluded.companion_resource_summary,
                hil_trigger_summary=excluded.hil_trigger_summary,
                degradation_policy=excluded.degradation_policy
            """,
            (
                constitution.connector_id,
                constitution.constitution_id,
                constitution.schema_version,
                constitution.authored_by,
                constitution.authored_at,
                constitution.last_proven_at,
                json.dumps(constitution.execution_phases, sort_keys=True),
                json.dumps(constitution.prerequisite_reads, sort_keys=True),
                json.dumps(constitution.conflict_analysis_rules, sort_keys=True),
                json.dumps(constitution.hil_gates, sort_keys=True),
                json.dumps(constitution.mutation_sequencing, sort_keys=True),
                json.dumps(constitution.verification_requirements, sort_keys=True),
                json.dumps(constitution.companion_resource_roles, sort_keys=True),
                constitution.precondition_summary,
                constitution.companion_resource_summary,
                constitution.hil_trigger_summary,
                constitution.degradation_policy,
            ),
        )
        self._db.commit()

    def get_constitution(self, connector_id: str) -> ConstitutionRecord | None:
        row = self._db.execute(
            "SELECT * FROM connector_constitutions WHERE connector_id = ?",
            (connector_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_constitution(row)

    def list_constitutions(self) -> list[ConstitutionRecord]:
        rows = self._db.execute("SELECT * FROM connector_constitutions").fetchall()
        return [self._row_to_constitution(r) for r in rows]

    # ── Bulk ────────────────────────────────────────────────────────────

    def load_from_manifest_batch(self, batch: CapabilityRegistrationBatch) -> LoadResult:
        """Atomic batch load: entire connector batch is admitted or none of it.

        Uses a single transaction so partial failure rolls back the
        connector and all capabilities.  Inserts are done raw (not via
        the public commit()-ing methods) so the transaction boundary
        is preserved.  FTS5 is rebuilt exactly once at the end.
        """
        try:
            self._db.execute("BEGIN IMMEDIATE")
            # --- connector ---
            self._db.execute(
                """
                INSERT INTO connectors (connector_id, label, connector_type, provider_type,
                    version, admission_verdict, registration_type, constitution_json,
                    policy_json, resource_kinds_json, guide_cards_json, domain_id,
                    created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(connector_id) DO UPDATE SET
                    label=excluded.label, connector_type=excluded.connector_type,
                    provider_type=excluded.provider_type, version=excluded.version,
                    admission_verdict=excluded.admission_verdict,
                    registration_type=excluded.registration_type,
                    constitution_json=excluded.constitution_json,
                    policy_json=excluded.policy_json,
                    resource_kinds_json=excluded.resource_kinds_json,
                    guide_cards_json=excluded.guide_cards_json,
                    domain_id=excluded.domain_id,
                    updated_at=excluded.updated_at
                """,
                (
                    batch.connector.connector_id,
                    batch.connector.label,
                    batch.connector.connector_type,
                    batch.connector.provider_type,
                    batch.connector.version,
                    batch.connector.admission_verdict,
                    batch.connector.registration_type,
                    json.dumps(batch.connector.constitution, sort_keys=True),
                    json.dumps(batch.connector.policy_declarations, sort_keys=True),
                    json.dumps(batch.connector.resource_kinds, sort_keys=True),
                    json.dumps(batch.connector.guide_cards, sort_keys=True),
                    batch.connector.domain_id,
                    batch.connector.created_at,
                    batch.connector.updated_at,
                ),
            )
            # --- capabilities (chunked insert, no per-row FTS rebuild) ---
            chunk_size = 25_000
            for i in range(0, len(batch.capabilities), chunk_size):
                chunk = batch.capabilities[i : i + chunk_size]
                self._db.executemany(
                    """
                    INSERT OR REPLACE INTO capabilities (capability_name, connector_id,
                        invocation_mode, action_name, effect, resource_kind, domain_id, family_id,
                        description,
                        required_inputs_json, optional_inputs_json, output_schema_ref,
                        safety_band_min, risk_class, idempotency, compensation_capability,
                        record_type, created_at, contract_json, synthetic)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            c.capability_name,
                            c.connector_id,
                            c.invocation_mode,
                            c.action_name,
                            c.effect,
                            c.resource_kind,
                            c.domain_id,
                            c.family_id,
                            c.description,
                            json.dumps(c.required_inputs, sort_keys=True),
                            json.dumps(c.optional_inputs, sort_keys=True),
                            c.output_schema_ref,
                            c.safety_band_min,
                            c.risk_class,
                            c.idempotency,
                            c.compensation_capability,
                            c.record_type,
                            c.created_at,
                            json.dumps(c.contract_json, sort_keys=True),
                            1 if c.synthetic else 0,
                        )
                        for c in chunk
                    ],
                )
            # --- resource kinds ---
            for rk in batch.resource_kinds:
                self._db.execute(
                    """
                    INSERT INTO resource_kinds (kind_id, connector_id, label, schema_json,
                        verifier_affordances_json, created_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(kind_id) DO UPDATE SET
                        connector_id=excluded.connector_id, label=excluded.label,
                        schema_json=excluded.schema_json,
                        verifier_affordances_json=excluded.verifier_affordances_json
                    """,
                    (
                        rk.kind_id,
                        rk.connector_id,
                        rk.label,
                        json.dumps(rk.schema, sort_keys=True),
                        json.dumps(rk.verifier_affordances, sort_keys=True),
                        rk.created_at,
                    ),
                )
            # --- constitution ---
            if batch.constitution is not None:
                c = batch.constitution
                self._db.execute(
                    """
                    INSERT INTO connector_constitutions (connector_id, constitution_id,
                        schema_version, authored_by, authored_at, last_proven_at,
                        execution_phases_json, prerequisite_reads_json,
                        conflict_analysis_rules_json, hil_gates_json,
                        mutation_sequencing_json, verification_requirements_json,
                        companion_resource_roles_json, precondition_summary,
                        companion_resource_summary, hil_trigger_summary, degradation_policy)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(connector_id) DO UPDATE SET
                        constitution_id=excluded.constitution_id,
                        schema_version=excluded.schema_version,
                        authored_by=excluded.authored_by,
                        authored_at=excluded.authored_at,
                        last_proven_at=excluded.last_proven_at,
                        execution_phases_json=excluded.execution_phases_json,
                        prerequisite_reads_json=excluded.prerequisite_reads_json,
                        conflict_analysis_rules_json=excluded.conflict_analysis_rules_json,
                        hil_gates_json=excluded.hil_gates_json,
                        mutation_sequencing_json=excluded.mutation_sequencing_json,
                        verification_requirements_json=excluded.verification_requirements_json,
                        companion_resource_roles_json=excluded.companion_resource_roles_json,
                        precondition_summary=excluded.precondition_summary,
                        companion_resource_summary=excluded.companion_resource_summary,
                        hil_trigger_summary=excluded.hil_trigger_summary,
                        degradation_policy=excluded.degradation_policy
                    """,
                    (
                        c.connector_id,
                        c.constitution_id,
                        c.schema_version,
                        c.authored_by,
                        c.authored_at,
                        c.last_proven_at,
                        json.dumps(c.execution_phases, sort_keys=True),
                        json.dumps(c.prerequisite_reads, sort_keys=True),
                        json.dumps(c.conflict_analysis_rules, sort_keys=True),
                        json.dumps(c.hil_gates, sort_keys=True),
                        json.dumps(c.mutation_sequencing, sort_keys=True),
                        json.dumps(c.verification_requirements, sort_keys=True),
                        json.dumps(c.companion_resource_roles, sort_keys=True),
                        c.precondition_summary,
                        c.companion_resource_summary,
                        c.hil_trigger_summary,
                        c.degradation_policy,
                    ),
                )
            self._db.execute("COMMIT")
            # Rebuild FTS5 once after the transaction commits
            self.rebuild_fts_index()
            return LoadResult(
                total_connectors=1,
                total_capabilities=len(batch.capabilities),
                admitted=len(batch.capabilities),
                rejected=0,
                errors=[],
            )
        except Exception as exc:
            try:
                self._db.execute("ROLLBACK")
            except Exception:
                pass
            return LoadResult(
                total_connectors=1,
                total_capabilities=len(batch.capabilities),
                admitted=0,
                rejected=len(batch.capabilities),
                errors=[f"batch load failed, rolled back: {exc}"],
            )

    # ── Graph ontology queries (for CapabilityTypeResolver) ────────────

    def resolve_concept(self, alias: str, domain: str = "") -> list[dict[str, Any]]:
        if domain:
            rows = self._db.execute(
                """
                SELECT alias, canonical_concept, domain, weight, generic, source
                FROM concept_aliases WHERE alias = ? AND (domain = ? OR domain IS NULL OR domain = '')
                ORDER BY weight DESC
                """,
                (alias, domain),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT alias, canonical_concept, domain, weight, generic, source
                FROM concept_aliases WHERE alias = ?
                ORDER BY weight DESC
                """,
                (alias,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_concept_resource_family(self, concept: str, domain: str = "") -> list[dict[str, Any]]:
        if domain:
            rows = self._db.execute(
                """
                SELECT concept, resource_family, domain, weight
                FROM concept_resource_edges WHERE concept = ? AND domain = ?
                ORDER BY weight DESC
                """,
                (concept, domain),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT concept, resource_family, domain, weight
                FROM concept_resource_edges WHERE concept = ?
                ORDER BY weight DESC
                """,
                (concept,),
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_operation(self, alias: str, effect: str = "") -> list[dict[str, Any]]:
        if effect:
            rows = self._db.execute(
                """
                SELECT alias, operation_family, effect, weight, generic
                FROM operation_aliases WHERE alias = ? AND effect = ?
                ORDER BY weight DESC
                """,
                (alias, effect),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT alias, operation_family, effect, weight, generic
                FROM operation_aliases WHERE alias = ?
                ORDER BY weight DESC
                """,
                (alias,),
            ).fetchall()
        return [dict(r) for r in rows]

    def lookup_capability_by_type(
        self,
        domain: str,
        resource_family: str,
        operation_family: str,
        effect: str,
    ) -> list[dict[str, Any]]:
        """Typed capability lookup in ``capability_type_index``.

        When *domain* is empty, the domain filter is skipped (domain-agnostic
        lookup).  When *operation_family* is empty, that filter is skipped
        (operation-agnostic — useful for broad hints like ``"read"`` where
        the index stores canonical operations like ``"list"``, ``"get"``).
        """
        sql = [
            "SELECT capability_name, connector_id, domain, resource_family,",
            "       operation_family, effect, side_effect_class, risk_class",
            "FROM capability_type_index WHERE 1=1",
        ]
        params: list[Any] = []
        if domain:
            sql.append("AND domain = ?")
            params.append(domain)
        if resource_family:
            sql.append("AND resource_family = ?")
            params.append(resource_family)
        if operation_family:
            sql.append("AND operation_family = ?")
            params.append(operation_family)
        if effect:
            sql.append("AND effect = ?")
            params.append(effect)
        rows = self._db.execute(" ".join(sql), params).fetchall()
        return [dict(r) for r in rows]

    # ── Graph ontology upserts ─────────────────────────────────────────

    def upsert_concept_alias(
        self,
        alias: str,
        canonical_concept: str,
        domain: str = "",
        weight: float = 1.0,
        generic: bool = False,
        source: str = "catalog",
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO concept_aliases (alias, canonical_concept, domain, weight, generic, source)
            VALUES (?,?,?,?,?,?)
            """,
            (alias, canonical_concept, domain, weight, 1 if generic else 0, source),
        )
        self._db.commit()

    def upsert_concept_resource_edge(
        self,
        concept: str,
        resource_family: str,
        domain: str,
        weight: float = 1.0,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO concept_resource_edges (concept, resource_family, domain, weight)
            VALUES (?,?,?,?)
            """,
            (concept, resource_family, domain, weight),
        )
        self._db.commit()

    def upsert_resource_connector_edge(
        self,
        domain: str,
        resource_family: str,
        connector_id: str,
        weight: float = 1.0,
        role: str = "primary",
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO resource_connector_edges (domain, resource_family, connector_id, weight, role)
            VALUES (?,?,?,?,?)
            """,
            (domain, resource_family, connector_id, weight, role),
        )
        self._db.commit()

    def upsert_operation_alias(
        self,
        alias: str,
        operation_family: str,
        effect: str,
        weight: float = 1.0,
        generic: bool = True,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO operation_aliases (alias, operation_family, effect, weight, generic)
            VALUES (?,?,?,?,?)
            """,
            (alias, operation_family, effect, weight, 1 if generic else 0),
        )
        self._db.commit()

    def upsert_operation_equivalence(
        self,
        canonical_operation: str,
        equivalent_operation: str,
        resource_family: str | None = None,
        domain: str | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO operation_equivalences (canonical_operation, equivalent_operation, resource_family, domain)
            VALUES (?,?,?,?)
            """,
            (canonical_operation, equivalent_operation, resource_family or "", domain or ""),
        )
        self._db.commit()

    def get_operation_equivalences(
        self, canonical_operation: str | None = None
    ) -> list[dict[str, Any]]:
        if canonical_operation is not None:
            rows = self._db.execute(
                """
                SELECT canonical_operation, equivalent_operation, resource_family, domain
                FROM operation_equivalences WHERE canonical_operation = ?
                """,
                (canonical_operation,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT canonical_operation, equivalent_operation, resource_family, domain FROM operation_equivalences"
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_capability_type_index(
        self,
        capability_name: str,
        connector_id: str,
        domain: str,
        resource_family: str,
        operation_family: str,
        effect: str,
        side_effect_class: str | None = None,
        risk_class: str | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO capability_type_index (capability_name, connector_id, domain,
                resource_family, operation_family, effect, side_effect_class, risk_class)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                capability_name,
                connector_id,
                domain,
                resource_family,
                operation_family,
                effect,
                side_effect_class,
                risk_class,
            ),
        )
        self._db.commit()

    # ── Row deserialisation helpers ─────────────────────────────────────

    def _row_to_connector(self, row: sqlite3.Row) -> ConnectorRecord:
        return ConnectorRecord(
            connector_id=row["connector_id"],
            label=row["label"],
            connector_type=row["connector_type"],
            provider_type=row["provider_type"],
            version=row["version"],
            admission_verdict=row["admission_verdict"],
            registration_type=row["registration_type"],
            constitution=json.loads(row["constitution_json"]),
            policy_declarations=json.loads(row["policy_json"]),
            resource_kinds=json.loads(row["resource_kinds_json"]),
            guide_cards=json.loads(
                row["guide_cards_json"] if "guide_cards_json" in row.keys() else "[]"
            ),
            domain_id=row["domain_id"] if "domain_id" in row.keys() else "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_capability(self, row: sqlite3.Row) -> CapabilityRecord:
        return CapabilityRecord(
            capability_name=row["capability_name"],
            connector_id=row["connector_id"],
            invocation_mode=row["invocation_mode"],
            action_name=row["action_name"],
            effect=row["effect"],
            resource_kind=row["resource_kind"],
            domain_id=row["domain_id"] if "domain_id" in row.keys() else "",
            family_id=row["family_id"] if "family_id" in row.keys() else None,
            description=row["description"],
            required_inputs=json.loads(row["required_inputs_json"]),
            optional_inputs=json.loads(row["optional_inputs_json"]),
            output_schema_ref=row["output_schema_ref"],
            safety_band_min=row["safety_band_min"],
            risk_class=row["risk_class"],
            idempotency=row["idempotency"],
            compensation_capability=row["compensation_capability"],
            record_type=row["record_type"],
            created_at=row["created_at"],
            contract_json=json.loads(row["contract_json"]),
            synthetic=bool(row["synthetic"]),
        )

    def _row_to_resource_kind(self, row: sqlite3.Row) -> ResourceKindRecord:
        return ResourceKindRecord(
            kind_id=row["kind_id"],
            connector_id=row["connector_id"],
            label=row["label"],
            schema=json.loads(row["schema_json"]),
            verifier_affordances=json.loads(row["verifier_affordances_json"]),
            created_at=row["created_at"],
        )

    def _row_to_constitution(self, row: sqlite3.Row) -> ConstitutionRecord:
        return ConstitutionRecord(
            connector_id=row["connector_id"],
            constitution_id=row["constitution_id"],
            schema_version=row["schema_version"],
            authored_by=row["authored_by"],
            authored_at=row["authored_at"],
            last_proven_at=row["last_proven_at"],
            execution_phases=json.loads(row["execution_phases_json"]),
            prerequisite_reads=json.loads(row["prerequisite_reads_json"]),
            conflict_analysis_rules=json.loads(row["conflict_analysis_rules_json"]),
            hil_gates=json.loads(row["hil_gates_json"]),
            mutation_sequencing=json.loads(row["mutation_sequencing_json"]),
            verification_requirements=json.loads(row["verification_requirements_json"]),
            companion_resource_roles=json.loads(row["companion_resource_roles_json"]),
            precondition_summary=row["precondition_summary"],
            companion_resource_summary=row["companion_resource_summary"],
            hil_trigger_summary=row["hil_trigger_summary"],
            degradation_policy=row["degradation_policy"],
        )
