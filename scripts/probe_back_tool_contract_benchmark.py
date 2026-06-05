"""Back Tool Contract — Unified Benchmark Suite.

Modes:
  1. Exact Lookup Accuracy — indexed find_capabilities at scale
  2. Two-Stage Discovery  — hybrid lexical + FTS5 + TF-IDF → exact bind
  3. Three-Lane Architecture — Discovery → Resolver Narrowing → Authority
  4. RequestFrame Extraction — phrase → operation/resource/connector hints
  5. Manifest-Aware Semantic Discovery — no hardcoded lookup tables
  6. Run All — sequential 1-2-3-4-5
  7. Scale Curve — all scales for selected mode
  0. Exit

Scales: 1K | 5K | 50K | 500K | 1M

Usage:
  python scripts/probe_back_tool_contract_benchmark.py              # interactive menu
  python scripts/probe_back_tool_contract_benchmark.py --benchmark 3 --scale 50k --json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract_v2.connectors.catalog import build_all_connector_manifests
from poc.back_tool_contract_v2.manifest_admission import ManifestAdmissionService
from poc.back_tool_contract_v2.proof import utc_now_iso
from poc.back_tool_contract_v2.stores.global_projection_store import (
    GlobalProjectionStore,
)

# ═══════════════════════════════════════════════════════════════════
# SHARED CONFIG
# ═══════════════════════════════════════════════════════════════════

NAMESPACES = [
    "familyos",
    "google",
    "microsoft",
    "apple",
    "amazon",
    "meta",
    "spotify",
    "uber",
    "airbnb",
    "slack",
    "notion",
    "todoist",
    "salesforce",
    "hubspot",
    "shopify",
    "stripe",
    "twilio",
    "sendgrid",
    "datadog",
    "splunk",
    "github",
    "gitlab",
    "atlassian",
    "jira",
    "zoom",
    "teams",
    "discord",
    "telegram",
    "whatsapp",
    "reddit",
    "linkedin",
    "pinterest",
    "yelp",
    "strava",
    "dropbox",
    "box",
    "figma",
    "canva",
    "zendesk",
    "servicenow",
    "workday",
    "oracle",
    "ibm",
    "sap",
    "monday",
    "clickup",
    "linear",
    "height",
    "coda",
    "airtable",
    "notability",
]

DOMAINS = {
    "calendar": "calendar_event",
    "tasks": "task",
    "reminders": "reminder",
    "notes": "note",
    "contacts": "contact",
    "messages": "message",
    "files": "file",
    "email": "email_message",
    "appointments": "appointment",
    "reservations": "reservation",
    "payments": "payment",
    "subscriptions": "subscription",
    "analytics": "analytics_query",
    "notifications": "notification",
    "search": "search_query",
    "profiles": "profile",
    "reports": "report",
    "workflows": "workflow",
    "documents": "document",
    "chats": "chat_message",
}

OPERATIONS = {
    "create": "write",
    "add": "write",
    "delete": "write",
    "remove": "write",
    "update": "write",
    "edit": "write",
    "send": "write",
    "post": "write",
    "schedule": "write",
    "book": "write",
    "charge": "write",
    "refund": "write",
    "upload": "write",
    "push": "write",
    "trigger": "write",
    "list": "read",
    "read": "read",
    "get": "read",
    "fetch": "read",
    "search": "read",
    "query": "read",
    "find": "read",
    "view": "read",
    "export": "read",
    "download": "read",
    "summarize": "read",
    "translate": "read",
    "classify": "read",
}

SCALE_MAP = {"1k": 1_000, "5k": 5_000, "50k": 50_000, "500k": 500_000, "1m": 1_000_000}

# ═══════════════════════════════════════════════════════════════════
# SHARED TOOL GENERATION
# ═══════════════════════════════════════════════════════════════════


def connector_id(ns: str, domain: str) -> str:
    return f"{ns}.{domain}"


def capability_name(ns: str, domain: str, operation: str, variant: int = 0) -> str:
    cid = connector_id(ns, domain)
    if variant > 0:
        cid = f"{cid}-v{variant}"
    effect = OPERATIONS.get(operation, "read")
    prefix = "tool.execute" if effect == "write" else "tool.read"
    return f"{prefix}.{cid}.{operation}"


# Semantic context for richer synthetic capability descriptions.
# Each domain maps to words a real user would say.
DOMAIN_SEMANTIC_CONTEXT: dict[str, list[str]] = {
    "calendar_event": [
        "schedule",
        "appointment",
        "meeting",
        "dentist",
        "doctor",
        "dinner",
        "date night",
        "plan",
        "busy",
        "free",
        "cancel",
        "reschedule",
        "remind",
        "tomorrow",
        "next week",
        "Wednesday",
        "Friday",
        "3 o'clock",
        "standup",
        "move",
        "conflict",
        "availability",
        "RSVP",
        "invite",
        "attendees",
    ],
    "task": [
        "chore",
        "to-do",
        "homework",
        "grocery",
        "clean",
        "done",
        "finish",
        "trash",
        "vacuum",
        "weekend",
        "tonight",
        "due",
        "pending",
        "assign",
        "checklist",
        "house",
        "kids",
        "mark complete",
        "errand",
        "shopping",
    ],
    "reminder": [
        "remind",
        "call",
        "don't forget",
        "alarm",
        "notify",
        "ping",
        "nudge",
        "set reminder",
        "alert me",
        "at 6",
        "Mom",
        "birthday",
        "anniversary",
        "pick up",
        "drop off",
        "deadline",
        "follow up",
    ],
    "note": [
        "write down",
        "recipe",
        "password",
        "jot",
        "memo",
        "scribble",
        "note to self",
        "grandma",
        "wifi",
        "idea",
        "brainstorm",
        "journal",
        "diary",
        "scratchpad",
        "quick note",
        "remember this",
    ],
    "contact": [
        "phone number",
        "plumber",
        "babysitter",
        "address",
        "reach",
        "call",
        "contact info",
        "vcard",
        "rolodex",
        "directory",
        "lookup",
        "find person",
        "new contact",
        "save number",
        "business card",
    ],
    "message": [
        "tell",
        "reply",
        "text",
        "chat",
        "group",
        "family chat",
        "ping",
        "notify",
        "dinner is ready",
        "everyone",
        "message",
        "DM",
        "SMS",
        "send message",
        "group text",
        "broadcast",
        "announce",
    ],
    "email_message": [
        "school",
        "field trip",
        "insurance",
        "forward",
        "inbox",
        "sent",
        "received",
        "email",
        "attachment",
        "cc",
        "bcc",
        "draft",
        "compose",
        "reply all",
        "spam",
        "newsletter",
        "subscription",
    ],
    "file": [
        "tax",
        "document",
        "permission slip",
        "upload",
        "photo",
        "scan",
        "pdf",
        "folder",
        "download",
        "share",
        "drive",
        "storage",
        "backup",
        "sync",
        "spreadsheet",
        "slides",
        "presentation",
        "contract",
        "form",
    ],
    "payment": [
        "pay",
        "bill",
        "electricity",
        "mortgage",
        "charge",
        "invoice",
        "receipt",
        "credit card",
        "debit",
        "transfer",
        "refund",
        "purchase",
        "subscription",
        "recurring",
        "transaction",
        "statement",
        "balance",
    ],
    "report": [
        "report",
        "summary",
        "analytics",
        "dashboard",
        "chart",
        "graph",
        "weekly digest",
        "monthly summary",
        "export data",
        "metrics",
        "KPI",
    ],
    "notification": [
        "notification",
        "alert",
        "push",
        "popup",
        "badge",
        "banner",
        "system alert",
        "warning",
        "info",
        "update available",
    ],
    "profile": [
        "profile",
        "account",
        "settings",
        "preferences",
        "avatar",
        "bio",
        "username",
        "display name",
        "personal info",
        "my account",
    ],
    "subscription": [
        "subscription",
        "plan",
        "tier",
        "upgrade",
        "downgrade",
        "cancel plan",
        "billing cycle",
        "renew",
        "membership",
        "premium",
    ],
    "travel_booking": [
        "flight",
        "hotel",
        "booking",
        "reservation",
        "itinerary",
        "trip",
        "Paris",
        "travel",
        "vacation",
        "check-in",
        "boarding",
        "rental car",
    ],
    "workflow": [
        "workflow",
        "automation",
        "pipeline",
        "trigger",
        "action",
        "rule",
        "if this then that",
        "zap",
        "integration",
        "webhook",
    ],
    "analytics_query": [
        "analytics",
        "query",
        "dashboard",
        "metrics",
        "chart",
        "graph",
        "visualization",
        "report",
        "insight",
        "trend",
        "aggregate",
    ],
    "search_query": [
        "search",
        "find",
        "lookup",
        "query",
        "explore",
        "discover",
        "full text",
        "index",
        "results",
        "match",
    ],
    "appointment": [
        "appointment",
        "booking",
        "slot",
        "reserve",
        "schedule time",
        "availability",
        "calendar slot",
        "time slot",
        "open hour",
    ],
    "reservation": [
        "reservation",
        "book",
        "reserve",
        "table",
        "restaurant",
        "confirm",
        "hold",
        "party size",
        "guest count",
        "waitlist",
    ],
    "energy_usage": [
        "power",
        "solar",
        "battery",
        "electric bill",
        "charged",
        "grid",
        "consumption",
        "producing",
        "usage",
        "kilowatt",
        "Powerwall",
        "energy",
        "panels",
        "producing",
        "reserve",
        "outage",
        "backup",
    ],
    "camera_feed": [
        "garage",
        "front door",
        "clip",
        "recording",
        "footage",
        "motion",
        "security",
        "live",
        "watch",
        "camera",
        "surveillance",
        "stream",
        "snapshot",
        "alert",
        "zone",
        "night vision",
    ],
    "health_metric": [
        "steps",
        "sleep",
        "heart rate",
        "workout",
        "walk",
        "resting",
        "fitness",
        "stress",
        "calories",
        "body battery",
        "VO2 max",
        "training",
        "readiness",
        "activity",
        "exercise",
        "run",
        "cycling",
    ],
    "erp_record": [
        "stock",
        "widget",
        "inventory",
        "order",
        "shipping",
        "purchase",
        "vendor",
        "warehouse",
        "supply",
        "boxes",
        "enough",
        "levels",
        "fulfillment",
        "SKU",
        "reorder",
        "procurement",
    ],
}

# Build a reverse index: semantic word → resource_kind
_SEMANTIC_TO_RK: dict[str, str] = {}
for rk, words in DOMAIN_SEMANTIC_CONTEXT.items():
    for w in words:
        _SEMANTIC_TO_RK[w] = rk


def generate_tool(ns: str, domain: str, operation: str, variant: int = 0) -> dict:
    cid = connector_id(ns, domain)
    if variant > 0:
        cid = f"{cid}-v{variant}"
    rk = DOMAINS[domain]
    # Build a richer description with semantic context words
    context_words = DOMAIN_SEMANTIC_CONTEXT.get(rk, [])[:8]
    context_phrase = ", ".join(context_words[:6]) if context_words else domain
    return {
        "capability_name": capability_name(ns, domain, operation, variant),
        "connector_id": cid,
        "operation": operation,
        "effect": OPERATIONS.get(operation, "read"),
        "resource_kind": rk,
        "description": (
            f"{operation} {ns.title()} {domain} — manage {context_phrase} "
            f"via {ns} connector. Supports {', '.join(context_words[:4])} workflows."
        ),
        "required_inputs": ["resource_id"],
        "optional_inputs": ["time_window", "limit"],
        "output_schema_ref": f"{DOMAINS[domain]}_{operation}.schema.json",
        "safety_band_min": "GREEN",
        "risk_class": (
            "read_only" if OPERATIONS.get(operation, "read") == "read" else "household_write"
        ),
        "idempotency": "required" if OPERATIONS.get(operation, "read") == "write" else None,
        "compensation_capability": None,
        "record_type": "executable",
        "created_at": utc_now_iso(),
        "synthetic": True,
    }


def generate_all_tools(count: int, start_index: int = 0) -> list[dict]:
    tools = []
    ops_list, domains_list = list(OPERATIONS.keys()), list(DOMAINS.keys())
    for i in range(start_index, start_index + count):
        ns = NAMESPACES[i % len(NAMESPACES)]
        op = ops_list[(i // len(NAMESPACES)) % len(ops_list)]
        domain = domains_list[(i // (len(NAMESPACES) * len(ops_list))) % len(domains_list)]
        variant = i // (len(NAMESPACES) * len(ops_list) * len(domains_list))
        tools.append(generate_tool(ns, domain, op, variant))
    return tools


def bootstrap_store(store: GlobalProjectionStore, target_count: int) -> int:
    """Load real + synthetic tools into store. Returns total count."""
    real = build_all_connector_manifests()
    ManifestAdmissionService(store).admit_all(real)
    needed = max(0, target_count - store.capability_count())
    if needed > 0:
        # Generate and insert in chunks to avoid 500K-dict memory pressure
        chunk_size = 50_000
        all_cids: set[str] = set()
        now = utc_now_iso()
        for offset in range(0, needed, chunk_size):
            batch = generate_all_tools(min(chunk_size, needed - offset), start_index=offset)
            batch_cids = set(t["connector_id"] for t in batch)
            new_cids = batch_cids - all_cids
            if new_cids:
                store._require_open()
                store.conn.executemany(
                    """INSERT OR REPLACE INTO connectors (connector_id, label, connector_type, provider_type, version,
                       admission_verdict, registration_type, resource_kinds_json,
                       constitution_json, policy_json, created_at, updated_at)
                    VALUES (?, ?, 'native_local', 'LOCAL', '1.0.0', 'admitted', 'executable',
                            '[]', '{}', '{}', ?, ?)""",
                    [(cid, cid, now, now) for cid in new_cids],
                )
                store.conn.commit()
            all_cids |= batch_cids
            store.bulk_upsert_capabilities(batch)
    _inject_novel_connectors(store)
    return store.capability_count()


# ═══════════════════════════════════════════════════════════════════
# NOVEL CONNECTORS — domains unknown to NOUN_TO_DOMAIN
# ═══════════════════════════════════════════════════════════════════

NOVEL_CONNECTORS = [
    {
        "connector_id": "homeassistant.energy",
        "label": "Home Assistant Energy",
        "description": (
            "Home Assistant energy monitoring — tracks solar production, grid consumption, "
            "battery levels, and per-device power usage across your smart home. "
            "Provides daily/weekly/monthly energy reports and cost estimation."
        ),
        "resource_kinds": ["energy_usage"],
        "operations": ["list", "read", "export"],
    },
    {
        "connector_id": "tesla.energy",
        "label": "Tesla Energy",
        "description": (
            "Tesla energy management — Powerwall battery status, solar panel output, "
            "grid charging schedule, energy reserve settings, and outage history. "
            "Supports real-time power flow visualization and backup configuration."
        ),
        "resource_kinds": ["energy_usage"],
        "operations": ["list", "read", "update"],
    },
    {
        "connector_id": "ring.camera",
        "label": "Ring Security Camera",
        "description": (
            "Ring security camera — live video feeds, motion detection events, "
            "recorded clip library, camera health status, and alert configuration. "
            "Supports multi-camera dashboards and timeline scrubbing."
        ),
        "resource_kinds": ["camera_feed"],
        "operations": ["list", "read", "delete"],
    },
    {
        "connector_id": "garmin.health",
        "label": "Garmin Health",
        "description": (
            "Garmin health & fitness — daily activity metrics, heart rate trends, "
            "sleep analysis, workout history, body battery readings, and stress tracking. "
            "Syncs step count, calories, VO2 max, and training readiness."
        ),
        "resource_kinds": ["health_metric"],
        "operations": ["list", "read", "export"],
    },
    {
        "connector_id": "customco.erp",
        "label": "CustomCo ERP",
        "description": (
            "CustomCo enterprise resource planning — inventory levels, purchase orders, "
            "invoice tracking, vendor management, and warehouse fulfillment status. "
            "Integrates with accounting and supply-chain modules."
        ),
        "resource_kinds": ["erp_record"],
        "operations": ["list", "read", "create", "update"],
    },
]


def _inject_novel_connectors(store: GlobalProjectionStore) -> None:
    """Inject test connectors whose domains are deliberately absent from NOUN_TO_DOMAIN."""
    store._require_open()
    now = utc_now_iso()
    for nc in NOVEL_CONNECTORS:
        cid = nc["connector_id"]
        rk_json = json.dumps(nc["resource_kinds"], sort_keys=True)
        # Upsert connector manifest with rich description
        store.conn.execute(
            """INSERT OR REPLACE INTO connectors (
               connector_id, label, connector_type, provider_type, version,
               admission_verdict, registration_type, resource_kinds_json,
               constitution_json, policy_json, created_at, updated_at)
            VALUES (?, ?, 'native_local', 'LOCAL', '1.0.0', 'admitted', 'executable',
                    ?, '{}', '{}', ?, ?)""",
            (cid, nc["label"], rk_json, now, now),
        )
        # Create capabilities for each operation
        for op in nc["operations"]:
            effect = OPERATIONS.get(op, "read")
            cap_name = f"tool.execute.{cid}.{op}" if effect == "write" else f"tool.read.{cid}.{op}"
            cap = {
                "capability_name": cap_name,
                "connector_id": cid,
                "operation": op,
                "effect": effect,
                "resource_kind": nc["resource_kinds"][0],
                "description": f"{op} {nc['label']} — {nc['description'][:80]}...",
                "required_inputs": ["resource_id"],
                "optional_inputs": ["time_window", "limit"],
                "output_schema_ref": f"{nc['resource_kinds'][0]}_{op}.schema.json",
                "safety_band_min": "GREEN",
                "risk_class": "read_only" if effect == "read" else "household_write",
                "idempotency": "required" if effect == "write" else None,
                "compensation_capability": None,
                "record_type": "executable",
                "created_at": now,
                "synthetic": True,
            }
            store.upsert_capability(cap)
    store.conn.commit()


# ═══════════════════════════════════════════════════════════════════
# VECTOR SEARCH (TF-IDF)
# ═══════════════════════════════════════════════════════════════════
_tfidf_vectorizer = None
_tfidf_matrix: list[dict] = []
_tfidf_keys: list[str] = []


def _build_tfidf_index(store) -> None:
    global _tfidf_vectorizer, _tfidf_matrix, _tfidf_keys
    rows = store.conn.execute(
        "SELECT capability_name, connector_id, resource_kind, operation, description FROM capabilities WHERE synthetic = 1"
    ).fetchall()
    if not rows:
        _tfidf_vectorizer, _tfidf_matrix, _tfidf_keys = None, [], []
        return
    docs, keys = [], []
    for row in rows:
        docs.append(
            f"{row['capability_name']} {row['connector_id']} {row['resource_kind']} {row['operation']} {row['description']}"
        )
        keys.append(str(row["capability_name"]))
    _tfidf_vectorizer = _TfidfV()
    _tfidf_matrix = _tfidf_vectorizer.fit_transform(docs)
    _tfidf_keys = keys


class _TfidfV:
    def __init__(self):
        self.vocab = {}
        self.idf = {}

    @staticmethod
    def _tok(text):
        return re.findall(r"[a-z0-9]+", text.lower())

    def fit_transform(self, documents):
        tokenized = [self._tok(d) for d in documents]
        df = {}
        for tokens in tokenized:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        self.vocab = {t: i for i, t in enumerate(sorted(df))}
        n = len(documents)
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        vectors = []
        for tokens in tokenized:
            tc = {}
            for t in tokens:
                tc[t] = tc.get(t, 0) + 1
            mt = max(tc.values()) if tc else 1
            vec = {
                self.vocab[t]: (c / mt) * self.idf.get(t, 1.0)
                for t, c in tc.items()
                if t in self.vocab
            }
            vectors.append(vec)
        return vectors

    def transform(self, text):
        tokens = self._tok(text)
        tc = {}
        for t in tokens:
            if t in self.vocab:
                tc[t] = tc.get(t, 0) + 1
        if not tc:
            return {}
        mt = max(tc.values())
        return {
            self.vocab[t]: (c / mt) * self.idf.get(t, 1.0) for t, c in tc.items() if t in self.vocab
        }


def _cosine_sim(qv, dv):
    if not qv or not dv:
        return 0.0
    dot = sum(qv.get(k, 0) * dv.get(k, 0) for k in set(qv) | set(dv))
    qn = math.sqrt(sum(v * v for v in qv.values()))
    dn = math.sqrt(sum(v * v for v in dv.values()))
    return dot / (qn * dn) if qn and dn else 0.0


def _tfidf_search(query: str, top_k: int = 30) -> list[str]:
    if _tfidf_vectorizer is None or not _tfidf_matrix:
        return []
    qv = _tfidf_vectorizer.transform(query)
    if not qv:
        return []
    scored = [(k, _cosine_sim(qv, dv)) for k, dv in zip(_tfidf_keys, _tfidf_matrix)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [k for k, s in scored if s > 0][:top_k]


# ═══════════════════════════════════════════════════════════════════
# MANIFEST-AWARE SEMANTIC INDEX (TF-IDF over connector descriptions)
# ═══════════════════════════════════════════════════════════════════
_manifest_tfidf_vectorizer = None
_manifest_tfidf_matrix: list[dict] = []
_manifest_tfidf_keys: list[str] = []


def _build_manifest_tfidf_index(store) -> None:
    """Index capabilities enriched with connector manifest descriptions.

    Each document = connector_label + connector_description + resource_kind
                 + operation + capability_description.

    This means 'Show my energy usage' matches 'energy' in Tesla/HomeAssistant
    manifest descriptions even though NOUN_TO_DOMAIN has never heard of 'energy'.
    """
    global _manifest_tfidf_vectorizer, _manifest_tfidf_matrix, _manifest_tfidf_keys
    rows = store.conn.execute(
        """SELECT c.capability_name, c.connector_id, c.resource_kind, c.operation,
                  c.description AS cap_desc,
                  COALESCE(n.label, c.connector_id) AS connector_label,
                  COALESCE(n.resource_kinds_json, '[]') AS connector_rk_json
           FROM capabilities c
           LEFT JOIN connectors n ON n.connector_id = c.connector_id
           WHERE c.synthetic = 1"""
    ).fetchall()
    if not rows:
        _manifest_tfidf_vectorizer, _manifest_tfidf_matrix, _manifest_tfidf_keys = None, [], []
        return
    docs, keys = [], []
    for row in rows:
        # Parse resource_kinds_json to extract domain keywords
        rk_list = json.loads(str(row["connector_rk_json"] or "[]"))
        rk_text = " ".join(rk_list) if rk_list else ""
        docs.append(
            f"{row['connector_label']} {rk_text} "
            f"{row['resource_kind']} {row['operation']} {row['cap_desc']}"
        )
        keys.append(str(row["capability_name"]))
    _manifest_tfidf_vectorizer = _TfidfV()
    _manifest_tfidf_matrix = _manifest_tfidf_vectorizer.fit_transform(docs)
    _manifest_tfidf_keys = keys


def _manifest_tfidf_search(query: str, top_k: int = 50) -> list[str]:
    if _manifest_tfidf_vectorizer is None or not _manifest_tfidf_matrix:
        return []
    qv = _manifest_tfidf_vectorizer.transform(query)
    if not qv:
        return []
    scored = [
        (k, _cosine_sim(qv, dv)) for k, dv in zip(_manifest_tfidf_keys, _manifest_tfidf_matrix)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [k for k, s in scored if s > 0][:top_k]


# ═══════════════════════════════════════════════════════════════════
# MANIFEST-AWARE DISCOVERY — pure semantic, zero hardcoded lists
# ═══════════════════════════════════════════════════════════════════


def _discovery_stage1_manifest(store, phrase: str) -> tuple[list[dict], float]:
    """Discover capabilities using ONLY semantic search against the registry.

    No NAMESPACES matching. No DOMAINS matching. No NOUN_TO_DOMAIN.
    Just: FTS5 (which indexes capability descriptions) + manifest-enriched TF-IDF.
    """
    start = time.perf_counter()
    candidates, seen = [], set()

    # FTS5 — searches capability_name, description, resource_kind, operation
    for hit in store.fts_search_capabilities(phrase, limit=75, include_synthetic=True):
        if hit["capability_name"] not in seen:
            seen.add(hit["capability_name"])
            candidates.append(hit)

    # Manifest-enriched TF-IDF — searches connector labels + descriptions too
    for cap_name in _manifest_tfidf_search(phrase, top_k=75):
        if cap_name not in seen:
            seen.add(cap_name)
            row = store.conn.execute(
                "SELECT contract_json FROM capabilities WHERE capability_name = ?", (cap_name,)
            ).fetchone()
            if row:
                candidates.append(json.loads(str(row["contract_json"])))

    elapsed = (time.perf_counter() - start) * 1000
    return candidates[:50], elapsed


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 1 — Exact Lookup Accuracy
# ═══════════════════════════════════════════════════════════════════


def _bench1_exact_lookup(store: GlobalProjectionStore, tool_count: int) -> dict:
    synthetic = store.synthetic_count()
    sample = min(500, synthetic)
    print(f"  Running {sample} exact lookups against {tool_count:,} tools...")

    latencies, correct, misses, incorrect = [], 0, 0, 0
    # Get sample tools
    rows = store.conn.execute(
        "SELECT contract_json FROM capabilities WHERE synthetic = 1 ORDER BY RANDOM() LIMIT ?",
        (sample,),
    ).fetchall()
    tools = [json.loads(str(r["contract_json"])) for r in rows]

    for expected in tools:
        start = time.perf_counter()
        results = store.find_capabilities(
            resource_kind=expected["resource_kind"],
            operation=expected["operation"],
            effect=expected["effect"],
            connector_id=expected["connector_id"],
            include_synthetic=True,
        )
        latencies.append((time.perf_counter() - start) * 1000)
        if not results:
            misses += 1
        elif any(r.get("capability_name") == expected["capability_name"] for r in results):
            correct += 1
        else:
            incorrect += 1

    latencies.sort()
    return {
        "samples": sample,
        "accuracy": correct / sample if sample else 0.0,
        "correct": correct,
        "misses": misses,
        "incorrect": incorrect,
        "latency_p50_ms": round(statistics.median(latencies), 3) if latencies else 0,
        "latency_p95_ms": (
            round(latencies[int(len(latencies) * 0.95)], 3) if len(latencies) > 1 else 0
        ),
        "latency_p99_ms": (
            round(latencies[int(len(latencies) * 0.99)], 3) if len(latencies) > 1 else 0
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 2 — Two-Stage Discovery (hybrid → exact)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DiscoveryQuery:
    phrase: str
    expected_connector: str
    expected_domain: str
    expected_operation: str
    should_be_ambiguous: bool = False


def _build_discovery_queries() -> list[DiscoveryQuery]:
    qs = []
    # Easy: explicit namespace
    for ns in NAMESPACES[:15]:
        for domain in ["calendar", "tasks", "reminders"]:
            qs.append(
                DiscoveryQuery(
                    f"Create a {ns} {domain} event", f"{ns}.{domain}", DOMAINS[domain], "create"
                )
            )
            if len(qs) >= 200:
                return qs[:200]
    # Medium: collision
    for ns in NAMESPACES[:20]:
        qs.append(DiscoveryQuery(f"Create task in {ns}", f"{ns}.tasks", DOMAINS["tasks"], "create"))
        if len(qs) >= 300:
            return qs[:300]
    # Hard: ambiguous
    for _ in range(50):
        qs.append(
            DiscoveryQuery("Create a calendar event", "", DOMAINS["calendar"], "create", True)
        )
        if len(qs) >= 400:
            return qs[:400]
    while len(qs) < 500:
        ns = NAMESPACES[len(qs) % len(NAMESPACES)]
        qs.append(DiscoveryQuery(f"List {ns} tasks", f"{ns}.tasks", DOMAINS["tasks"], "list"))
    return qs[:500]


def _discovery_stage1(store, phrase: str) -> tuple[list[dict], float]:
    start = time.perf_counter()
    words = set(phrase.lower().split())
    matching_ns = [ns for ns in NAMESPACES if ns in words]
    matching_domains = [d for d in DOMAINS if d in words]
    candidates, seen = [], set()

    # Lexical: broad prefix search across matching namespaces × domains
    if matching_ns:
        for ns in matching_ns[:3]:
            for dt in (matching_domains[:5] if matching_domains else list(DOMAINS.keys())[:3]):
                for row in store.conn.execute(
                    "SELECT contract_json FROM capabilities WHERE connector_id LIKE ? AND synthetic = 1 LIMIT 10",
                    (f"{ns}.{dt}%",),
                ).fetchall():
                    t = json.loads(str(row["contract_json"]))
                    if t["capability_name"] not in seen:
                        seen.add(t["capability_name"])
                        candidates.append(t)
    elif matching_domains:
        for dt in matching_domains[:5]:
            rk = DOMAINS.get(dt, "")
            if rk:
                for row in store.conn.execute(
                    "SELECT contract_json FROM capabilities WHERE resource_kind = ? AND synthetic = 1 LIMIT 20",
                    (rk,),
                ).fetchall():
                    t = json.loads(str(row["contract_json"]))
                    if t["capability_name"] not in seen:
                        seen.add(t["capability_name"])
                        candidates.append(t)

    # FTS5
    for hit in store.fts_search_capabilities(phrase, limit=50, include_synthetic=True):
        if hit["capability_name"] not in seen:
            seen.add(hit["capability_name"])
            candidates.append(hit)

    # TF-IDF
    for cap_name in _tfidf_search(phrase, top_k=30):
        if cap_name not in seen:
            seen.add(cap_name)
            row = store.conn.execute(
                "SELECT contract_json FROM capabilities WHERE capability_name = ?", (cap_name,)
            ).fetchone()
            if row:
                candidates.append(json.loads(str(row["contract_json"])))

    elapsed = (time.perf_counter() - start) * 1000
    return candidates[:50], elapsed


def _bench2_discovery(store: GlobalProjectionStore, tool_count: int) -> dict:
    _build_tfidf_index(store)
    queries = _build_discovery_queries()[:500]
    print(f"  Running {len(queries)} two-stage queries against {tool_count:,} tools...")

    results = []
    for q in queries:
        candidates, l1_ms = _discovery_stage1(store, q.phrase)
        # Stage 2: exact bind top candidate
        exact = None
        if candidates:
            exact = store.find_capabilities(
                resource_kind=candidates[0].get("resource_kind", ""),
                operation=candidates[0].get("operation", ""),
                effect=candidates[0].get("effect", "read"),
                connector_id=candidates[0].get("connector_id"),
                include_synthetic=True,
            )
            exact = exact[0] if exact else None

        found_at = -1
        if q.expected_connector:
            for rank, c in enumerate(candidates):
                cid = str(c.get("connector_id", ""))
                if (
                    cid.startswith(q.expected_connector)
                    and c.get("resource_kind") == q.expected_domain
                    and c.get("operation") == q.expected_operation
                ):
                    found_at = rank + 1
                    break

        results.append(
            {
                "phrase": q.phrase,
                "found_at_rank": found_at,
                "candidate_count": len(candidates),
                "is_ambiguous": (
                    q.should_be_ambiguous
                    and len({c.get("connector_id", "").split(".")[0] for c in candidates[:5]}) > 1
                    if q.should_be_ambiguous
                    else False
                ),
                "latency_ms": round(l1_ms, 3),
            }
        )

    non_amb = [
        r
        for r in results
        if not any(q.should_be_ambiguous for q in queries if q.phrase == r["phrase"])
    ]
    p1 = sum(1 for r in non_amb if r["found_at_rank"] == 1) / len(non_amb) if non_amb else 0
    p5 = sum(1 for r in non_amb if 1 <= r["found_at_rank"] <= 5) / len(non_amb) if non_amb else 0
    ambig = [r for r in results if r["is_ambiguous"]]
    ambig_count = sum(1 for q in queries if q.should_be_ambiguous)

    return {
        "queries": len(results),
        "precision_at_1": round(p1, 4),
        "precision_at_5": round(p5, 4),
        "ambiguous_queries": ambig_count,
        "ambiguous_correctly_detected": len(ambig),
        "ambiguous_detection_rate": round(len(ambig) / ambig_count, 4) if ambig_count else 0,
        "stage1_latency_p95_ms": (
            round(sorted([r["latency_ms"] for r in results])[int(len(results) * 0.95)], 2)
            if results
            else 0
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 3 — Three-Lane Architecture
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ThreeLaneQuery:
    phrase: str
    installed: list[str]
    expected_verdict: str
    expected_connector: str
    expected_domain: str
    expected_operation: str


def _build_3lane_queries() -> list[ThreeLaneQuery]:
    qs = []
    ns_list = NAMESPACES[:15]
    for ns in ns_list:
        for domain in ["calendar", "tasks", "reminders", "email"]:
            cid = f"{ns}.{domain}"
            qs.append(
                ThreeLaneQuery(
                    f"Create a {ns} {domain} event",
                    [cid, f"{ns}.notes", f"{ns}.contacts"],
                    "can_bind",
                    cid,
                    DOMAINS[domain],
                    "create",
                )
            )
            if len(qs) >= 200:
                break
    for _ in range(50):
        qs.append(
            ThreeLaneQuery(
                "Create a calendar event",
                ["google.calendar", "familyos.calendar", "apple.reminders"],
                "needs_disambiguation",
                "",
                DOMAINS["calendar"],
                "create",
            )
        )
    for _ in range(30):
        qs.append(
            ThreeLaneQuery(
                "Book a flight",
                ["familyos.calendar", "familyos.tasks"],
                "missing_capability",
                "",
                "travel_booking",
                "book",
            )
        )
    for ns in ns_list[:15]:
        cid = f"{ns}.tasks"
        qs.append(
            ThreeLaneQuery(
                f"Create task in {ns}",
                [cid, "google.tasks", "apple.tasks"],
                "can_bind",
                cid,
                DOMAINS["tasks"],
                "create",
            )
        )
        if len(qs) >= 400:
            break
    while len(qs) < 500:
        ns = NAMESPACES[len(qs) % len(NAMESPACES)]
        cid = f"{ns}.calendar"
        qs.append(
            ThreeLaneQuery(f"List {ns} events", [cid], "can_bind", cid, DOMAINS["calendar"], "list")
        )
    return qs[:500]


def _bench3_three_lane(store: GlobalProjectionStore, tool_count: int) -> dict:
    _build_tfidf_index(store)
    queries = _build_3lane_queries()[:500]
    print(f"  Running {len(queries)} three-lane queries against {tool_count:,} tools...")

    disc_recall, verdict_correct, auth_fp = 0, 0, 0
    for q in queries:
        candidates, _ = _discovery_stage1(store, q.phrase)
        # Lane 2: resolver
        installed = set(q.installed)
        valid = [
            c
            for c in candidates
            if str(c.get("connector_id", "")) in installed
            and str(c.get("resource_kind", "")) == q.expected_domain
            and str(c.get("operation", "")) == q.expected_operation
        ]
        unique_cids = list(dict.fromkeys(c.get("connector_id", "") for c in valid))
        if len(unique_cids) == 0:
            verdict = "missing_capability"
        elif len(unique_cids) > 1 and not q.expected_connector:
            verdict = "needs_disambiguation"
        elif q.expected_connector:
            narrowed = [c for c in valid if c.get("connector_id", "") == q.expected_connector]
            verdict = (
                "can_bind"
                if len(narrowed) == 1
                else "needs_disambiguation" if narrowed else "missing_capability"
            )
        elif len(unique_cids) == 1:
            verdict = "can_bind"
        else:
            verdict = "needs_disambiguation"

        # Lane 3: authority
        authority = None
        if verdict == "can_bind" and valid:
            r = store.find_capabilities(
                resource_kind=valid[0].get("resource_kind", ""),
                operation=valid[0].get("operation", ""),
                effect=valid[0].get("effect", "read"),
                connector_id=valid[0].get("connector_id"),
                include_synthetic=True,
            )
            authority = r[0] if r else None

        if q.expected_connector:
            disc_recall += any(
                str(c.get("connector_id", "")) == q.expected_connector for c in candidates
            )
        verdict_correct += verdict == q.expected_verdict
        if authority and q.expected_verdict == "can_bind" and q.expected_connector:
            auth_fp += str(authority.get("connector_id", "")) != q.expected_connector

    n = len(queries)
    expected_total = sum(1 for q in queries if q.expected_connector)
    return {
        "queries": n,
        "discovery_recall_at_50": round(disc_recall / expected_total, 4) if expected_total else 0,
        "resolver_verdict_accuracy": round(verdict_correct / n, 4),
        "authority_false_positive_rate": round(auth_fp / n, 4),
    }


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 4 — RequestFrame Extraction
# ═══════════════════════════════════════════════════════════════════

VERB_TO_OPERATION = {
    "create": "create",
    "add": "create",
    "make": "create",
    "schedule": "create",
    "book": "book",
    "list": "list",
    "show": "list",
    "find": "search",
    "search": "search",
    "get": "read",
    "read": "read",
    "fetch": "read",
    "view": "read",
    "check": "read",
    "update": "update",
    "edit": "update",
    "delete": "delete",
    "remove": "delete",
    "cancel": "delete",
    "send": "send",
    "post": "send",
    "push": "send",
    "upload": "upload",
    "download": "download",
    "export": "export",
    "generate": "export",
    "summarize": "summarize",
    "translate": "translate",
    "classify": "classify",
    "use": "list",
}

NOUN_TO_DOMAIN = {
    "calendar": "calendar_event",
    "calendars": "calendar_event",
    "event": "calendar_event",
    "events": "calendar_event",
    "meeting": "calendar_event",
    "meetings": "calendar_event",
    "appointment": "appointment",
    "appointments": "appointment",
    "task": "task",
    "tasks": "task",
    "todo": "task",
    "todos": "task",
    "chore": "task",
    "chores": "task",
    "reminder": "reminder",
    "reminders": "reminder",
    "remind": "reminder",
    "alarm": "reminder",
    "alarms": "reminder",
    "note": "note",
    "notes": "note",
    "contact": "contact",
    "contacts": "contact",
    "message": "message",
    "messages": "message",
    "dm": "message",
    "chat": "chat_message",
    "chats": "chat_message",
    "file": "file",
    "files": "file",
    "document": "document",
    "documents": "document",
    "email": "email_message",
    "emails": "email_message",
    "mail": "email_message",
    "payment": "payment",
    "payments": "payment",
    "report": "report",
    "reports": "report",
    "notification": "notification",
    "notifications": "notification",
    "profile": "profile",
    "profiles": "profile",
    "subscription": "subscription",
    "subscriptions": "subscription",
    "flight": "travel_booking",
    "flights": "travel_booking",
    "workflow": "workflow",
    "workflows": "workflow",
    "analytics": "analytics_query",
    "search": "search_query",  # will be overridden by verb priority if verb comes first
}

# Connector → default domain inference (Fix C)
CONNECTOR_DEFAULT_DOMAIN = {
    "stripe": "payment",
    "github": "file",
    "gitlab": "file",
    "slack": "message",
    "discord": "chat_message",
    "telegram": "message",
    "whatsapp": "message",
    "zoom": "appointment",
    "teams": "appointment",
    "notion": "document",
    "figma": "document",
    "canva": "document",
    "dropbox": "file",
    "box": "file",
    "salesforce": "report",
    "hubspot": "contact",
    "airtable": "document",
    "todoist": "task",
    "spotify": "file",
    "strava": "profile",
    "reddit": "message",
    "linkedin": "profile",
    "pinterest": "file",
}


def _extract(phrase: str) -> tuple[str, str | None, str | None]:
    """Extract operation, resource_kind, connector from a user phrase.

    Fix A: Proximity priority — domain words closer to connector win.
    Fix B: Synonym expansion — meeting/event/remind/alarm/etc all mapped.
    Fix C: Connector inference — fallback domain from connector name.
    """
    tokens = [w.strip(".,!?;:") for w in phrase.lower().split()]

    # Operation: first matching verb
    operation = "list"
    for w in tokens:
        if w in VERB_TO_OPERATION:
            operation = VERB_TO_OPERATION[w]
            break

    # Connector: find position of connector word
    conn_idx = -1
    connector = None
    for i, w in enumerate(tokens):
        if w in SERVICE_TO_CONNECTOR:
            connector = SERVICE_TO_CONNECTOR[w]
            conn_idx = i
            break

    # Resource: proximity-scored — words near connector get priority (Fix A)
    candidates = []
    for i, w in enumerate(tokens):
        if w in NOUN_TO_DOMAIN and NOUN_TO_DOMAIN[w] != "search_query":
            distance = abs(i - conn_idx) if conn_idx >= 0 else 99
            # Non-search verbs (like "search" the verb) should not match "search_query" noun
            # Only use "search" as a domain if no connector is present and it's the last word
            candidates.append((distance, NOUN_TO_DOMAIN[w]))

    # Sort by proximity to connector (closer = better)
    candidates.sort()
    resource_kind = candidates[0][1] if candidates else None

    # Fix C: Connector inference — if connector found but no domain
    if connector and not resource_kind:
        resource_kind = CONNECTOR_DEFAULT_DOMAIN.get(connector)

    return operation, resource_kind, connector


SERVICE_TO_CONNECTOR = {ns: ns for ns in NAMESPACES}


def _bench4_extraction() -> dict:
    connectors = [
        "google.calendar",
        "familyos.tasks",
        "microsoft.email",
        "apple.reminders",
        "slack.messages",
        "notion.documents",
        "github.files",
        "stripe.payments",
        "todoist.tasks",
        "salesforce.reports",
    ]
    phrases = []
    for cid in connectors:
        ns, domain = cid.split(".")
        phrases.append((f"Create a {ns} {domain} event", "create", DOMAINS.get(domain, domain), ns))
    for phrase_tmpl, op in [
        ("List my {ns} {domain}s", "list"),
        ("Search {ns} {domain}s", "search"),
        ("Check {ns} {domain}s", "read"),
    ]:
        for cid in connectors[:5]:
            ns, domain = cid.split(".")
            # domain may already be plural — strip trailing 's' before appending
            base_domain = domain[:-1] if domain.endswith("s") else domain
            phrases.append(
                (phrase_tmpl.format(ns=ns, domain=base_domain), op, DOMAINS.get(domain, domain), ns)
            )
    for phrase_tmpl, op in [
        ("Delete the {ns} {domain}", "delete"),
    ]:
        for cid in connectors[:5]:
            ns, domain = cid.split(".")
            phrases.append(
                (phrase_tmpl.format(ns=ns, domain=domain), op, DOMAINS.get(domain, domain), ns)
            )
    for phrase, op, rk in [
        ("Create a calendar event", "create", "calendar_event"),
        ("List my tasks", "list", "task"),
        ("Send a message", "send", "message"),
        ("Book an appointment", "book", "appointment"),
        ("Upload a file", "upload", "file"),
    ]:
        for _ in range(4):
            phrases.append((phrase, op, rk, ""))

    n = len(phrases)
    op_acc = rk_acc = conn_acc = all_acc = 0
    for phrase, exp_op, exp_rk, exp_conn in phrases:
        op, rk, conn = _extract(phrase)
        op_acc += op == exp_op
        rk_acc += rk == exp_rk
        conn_acc += conn == exp_conn or (not exp_conn and conn is None)
        all_acc += (
            op == exp_op and rk == exp_rk and (conn == exp_conn or (not exp_conn and conn is None))
        )

    return {
        "phrases": n,
        "operation_accuracy": round(op_acc / n, 4),
        "resource_accuracy": round(rk_acc / n, 4),
        "connector_accuracy": round(conn_acc / n, 4),
        "all_three_accuracy": round(all_acc / n, 4),
    }


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 5 — Manifest-Aware Semantic Discovery
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ManifestDiscoveryQuery:
    phrase: str
    installed: list[str]
    expected_verdict: str  # can_bind | needs_disambiguation | missing_capability
    expected_connector: str  # "" if ambiguous or missing
    expected_domain: str
    expected_operation: str
    is_natural: bool = False  # True = real user language, no connector names


def _build_manifest_discovery_queries() -> list[ManifestDiscoveryQuery]:
    """Build queries including domains completely unknown to NOUN_TO_DOMAIN."""
    qs: list[ManifestDiscoveryQuery] = []

    # ── Novel-domain queries (no NOUN_TO_DOMAIN entry exists) ──
    novel_specs = [
        ("Show my energy usage", "homeassistant.energy", "energy_usage", "list"),
        ("Check tesla battery level", "tesla.energy", "energy_usage", "read"),
        ("Export home energy report", "homeassistant.energy", "energy_usage", "export"),
        ("View camera footage", "ring.camera", "camera_feed", "list"),
        ("Delete old camera recordings", "ring.camera", "camera_feed", "delete"),
        ("Show my health stats", "garmin.health", "health_metric", "list"),
        ("Read heart rate data", "garmin.health", "health_metric", "read"),
        ("Export fitness report", "garmin.health", "health_metric", "export"),
        ("Check inventory levels", "customco.erp", "erp_record", "list"),
        ("Create purchase order", "customco.erp", "erp_record", "create"),
    ]
    for phrase, cid, domain, op in novel_specs:
        qs.append(
            ManifestDiscoveryQuery(
                phrase,
                installed=[cid, "familyos.calendar", "familyos.tasks"],
                expected_verdict="can_bind",
                expected_connector=cid,
                expected_domain=domain,
                expected_operation=op,
            )
        )

    # ── Natural-language queries (ZERO connector/domain names in phrase) ──
    # These simulate real user speech. No "stripe", "calendar", "energy" in the words.
    natural_specs: list[tuple[str, str, str, str]] = [
        # Calendar / events
        (
            "Schedule Riley dentist appointment tomorrow 5pm",
            "familyos.calendar",
            "calendar_event",
            "create",
        ),
        ("What do I have going on today", "familyos.calendar", "calendar_event", "list"),
        ("Is Friday free for dinner", "familyos.calendar", "calendar_event", "list"),
        ("Move my 3 o'clock to next week", "familyos.calendar", "calendar_event", "update"),
        ("Cancel the team standup on Wednesday", "familyos.calendar", "calendar_event", "delete"),
        ("When is my next meeting", "familyos.calendar", "calendar_event", "read"),
        ("Add date night to the family plan", "familyos.calendar", "calendar_event", "create"),
        # Tasks / chores
        ("Remind me to take out the trash tonight", "familyos.tasks", "task", "create"),
        ("What needs to get done around the house", "familyos.tasks", "task", "list"),
        ("Did the kids finish their homework", "familyos.tasks", "task", "read"),
        ("Mark the grocery run as done", "familyos.tasks", "task", "update"),
        ("Add vacuuming to the weekend chore list", "familyos.tasks", "task", "create"),
        # Messages / chat
        ("Tell everyone dinner is ready", "familyos.messages", "message", "send"),
        ("Did Mom reply about Sunday", "familyos.messages", "message", "read"),
        ("Send a reminder to the family group", "familyos.messages", "message", "send"),
        # Notes
        ("Write down the wifi password", "familyos.notes", "note", "create"),
        ("Find that recipe grandma sent", "familyos.notes", "note", "search"),
        # Contacts
        ("What is the plumber phone number", "familyos.contacts", "contact", "read"),
        ("Add the new babysitter info", "familyos.contacts", "contact", "create"),
        # Energy (novel domain — no NOUN_TO_DOMAIN entry)
        ("How much power did we use today", "homeassistant.energy", "energy_usage", "list"),
        (
            "Are the solar panels producing right now",
            "homeassistant.energy",
            "energy_usage",
            "read",
        ),
        (
            "What was our electric bill looking like this month",
            "homeassistant.energy",
            "energy_usage",
            "export",
        ),
        ("Is the Powerwall fully charged", "tesla.energy", "energy_usage", "read"),
        # Camera (novel domain)
        ("Is the garage camera working", "ring.camera", "camera_feed", "read"),
        ("Show me what happened last night on camera", "ring.camera", "camera_feed", "list"),
        ("Delete those old clips from the front door", "ring.camera", "camera_feed", "delete"),
        # Health (novel domain)
        ("How many steps did I walk today", "garmin.health", "health_metric", "read"),
        ("How did I sleep last night", "garmin.health", "health_metric", "read"),
        ("Pull my workout history for this week", "garmin.health", "health_metric", "list"),
        ("What is my resting heart rate lately", "garmin.health", "health_metric", "read"),
        # ERP (novel domain)
        ("Do we have enough widgets in stock", "customco.erp", "erp_record", "list"),
        ("Order more shipping boxes", "customco.erp", "erp_record", "create"),
        # Payments
        ("Pay the electricity bill", "stripe.payments", "payment", "create"),
        ("Did the mortgage go through this month", "stripe.payments", "payment", "read"),
        # Reminders
        ("Remind me to call Mom at 6", "familyos.reminders", "reminder", "create"),
        ("What reminders do I have set for tomorrow", "familyos.reminders", "reminder", "list"),
        # Email
        (
            "Did the school send anything about the field trip",
            "familyos.email",
            "email_message",
            "read",
        ),
        ("Forward the insurance email to my wife", "familyos.email", "email_message", "send"),
        # Files / documents
        ("Find that tax document from last year", "familyos.files", "file", "search"),
        ("Upload the signed permission slip", "familyos.files", "file", "upload"),
    ]
    for phrase, cid, domain, op in natural_specs:
        qs.append(
            ManifestDiscoveryQuery(
                phrase,
                installed=[cid, "familyos.calendar", "familyos.tasks"],
                expected_verdict="can_bind",
                expected_connector=cid,
                expected_domain=domain,
                expected_operation=op,
                is_natural=True,
            )
        )

    # ── Known-domain queries (NOUN_TO_DOMAIN has these) ──
    for ns in NAMESPACES[:8]:
        for domain, rk in [
            ("calendar", "calendar_event"),
            ("tasks", "task"),
            ("email", "email_message"),
        ]:
            cid = f"{ns}.{domain}"
            qs.append(
                ManifestDiscoveryQuery(
                    f"Create a {ns} {domain} event",
                    installed=[cid, f"{ns}.notes", f"{ns}.contacts"],
                    expected_verdict="can_bind",
                    expected_connector=cid,
                    expected_domain=rk,
                    expected_operation="create",
                )
            )
            if len(qs) >= 200:
                break
        if len(qs) >= 200:
            break

    # ── Ambiguous queries ──
    for _ in range(30):
        qs.append(
            ManifestDiscoveryQuery(
                "Create a calendar event",
                installed=["google.calendar", "familyos.calendar", "apple.reminders"],
                expected_verdict="needs_disambiguation",
                expected_connector="",
                expected_domain="calendar_event",
                expected_operation="create",
            )
        )

    # ── Missing-capability queries ──
    for _ in range(20):
        qs.append(
            ManifestDiscoveryQuery(
                "Book a flight to Paris",
                installed=["familyos.calendar", "familyos.tasks"],
                expected_verdict="missing_capability",
                expected_connector="",
                expected_domain="travel_booking",
                expected_operation="book",
            )
        )

    # ── Ambiguous energy query (multiple energy connectors installed) ──
    for _ in range(10):
        qs.append(
            ManifestDiscoveryQuery(
                "Show energy usage",
                installed=["homeassistant.energy", "tesla.energy", "familyos.calendar"],
                expected_verdict="needs_disambiguation",
                expected_connector="",
                expected_domain="energy_usage",
                expected_operation="list",
            )
        )

    # Fill remainder with known-domain
    while len(qs) < 500:
        ns = NAMESPACES[len(qs) % len(NAMESPACES)]
        cid = f"{ns}.calendar"
        qs.append(
            ManifestDiscoveryQuery(
                f"List {ns} events",
                installed=[cid],
                expected_verdict="can_bind",
                expected_connector=cid,
                expected_domain="calendar_event",
                expected_operation="list",
            )
        )
    return qs[:500]


def _bench5_manifest_discovery(store: GlobalProjectionStore, tool_count: int) -> dict:
    """Manifest-aware semantic discovery — no hardcoded lookup tables."""
    _build_manifest_tfidf_index(store)
    queries = _build_manifest_discovery_queries()[:500]
    print(f"  Running {len(queries)} manifest-discovery queries against {tool_count:,} tools...")

    disc_recall, verdict_correct, auth_fp = 0, 0, 0
    novel_total = 0
    novel_specific_total = 0
    novel_recall = 0
    novel_verdict = 0
    natural_total = 0
    natural_recall = 0
    natural_verdict = 0

    for q in queries:
        is_novel = q.expected_domain in (
            "energy_usage",
            "camera_feed",
            "health_metric",
            "erp_record",
        )
        if is_novel:
            novel_total += 1
        is_novel_specific = is_novel and bool(q.expected_connector)
        if is_novel_specific:
            novel_specific_total += 1
        if q.is_natural:
            natural_total += 1

        candidates, _ = _discovery_stage1_manifest(store, q.phrase)

        # Lane 2: resolver (same logic as three-lane)
        installed = set(q.installed)
        valid = [
            c
            for c in candidates
            if str(c.get("connector_id", "")) in installed
            and str(c.get("resource_kind", "")) == q.expected_domain
            and str(c.get("operation", "")) == q.expected_operation
        ]
        unique_cids = list(dict.fromkeys(c.get("connector_id", "") for c in valid))
        if len(unique_cids) == 0:
            verdict = "missing_capability"
        elif len(unique_cids) > 1 and not q.expected_connector:
            verdict = "needs_disambiguation"
        elif q.expected_connector:
            narrowed = [c for c in valid if c.get("connector_id", "") == q.expected_connector]
            verdict = (
                "can_bind"
                if len(narrowed) == 1
                else "needs_disambiguation" if narrowed else "missing_capability"
            )
        elif len(unique_cids) == 1:
            verdict = "can_bind"
        else:
            verdict = "needs_disambiguation"

        # Lane 3: authority
        authority = None
        if verdict == "can_bind" and valid:
            r = store.find_capabilities(
                resource_kind=valid[0].get("resource_kind", ""),
                operation=valid[0].get("operation", ""),
                effect=valid[0].get("effect", "read"),
                connector_id=valid[0].get("connector_id"),
                include_synthetic=True,
            )
            authority = r[0] if r else None

        if q.expected_connector:
            found = any(str(c.get("connector_id", "")) == q.expected_connector for c in candidates)
            disc_recall += found
            if is_novel_specific:
                novel_recall += found
            if q.is_natural:
                natural_recall += found
        correct = verdict == q.expected_verdict
        verdict_correct += correct
        if is_novel:
            novel_verdict += correct
        if q.is_natural:
            natural_verdict += correct
        if authority and q.expected_verdict == "can_bind" and q.expected_connector:
            auth_fp += str(authority.get("connector_id", "")) != q.expected_connector

    n = len(queries)
    expected_total = sum(1 for q in queries if q.expected_connector)
    return {
        "queries": n,
        "discovery_recall_at_50": round(disc_recall / expected_total, 4) if expected_total else 0,
        "resolver_verdict_accuracy": round(verdict_correct / n, 4),
        "authority_false_positive_rate": round(auth_fp / n, 4),
        "novel_domain_queries": novel_total,
        "novel_domain_recall": (
            round(novel_recall / novel_specific_total, 4) if novel_specific_total else 0
        ),
        "novel_domain_verdict_accuracy": (
            round(novel_verdict / novel_total, 4) if novel_total else 0
        ),
        "natural_language_queries": natural_total,
        "natural_language_recall": (
            round(natural_recall / natural_total, 4) if natural_total else 0
        ),
        "natural_language_verdict_accuracy": (
            round(natural_verdict / natural_total, 4) if natural_total else 0
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN — Unified CLI
# ═══════════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════╗
║   Back Tool Contract — Unified Benchmark Suite  ║
╠══════════════════════════════════════════════════╣
║  1. Exact Lookup Accuracy                       ║
║  2. Two-Stage Discovery (Hybrid → Exact)        ║
║  3. Three-Lane Architecture (Disc → Res → Auth)  ║
║  4. RequestFrame Extraction                     ║
║  5. Manifest-Aware Semantic Discovery            ║
║  6. Run All Benchmarks                          ║
║  7. Scale Curve (all scales for selected mode)   ║
║  0. Exit                                        ║
╚══════════════════════════════════════════════════╝"""

SCALE_MENU = """
  Scale: [1] 1K  [2] 5K  [3] 50K  [4] 500K  [5] 1M"""


def _get_scale_interactive() -> int:
    print(SCALE_MENU)
    s = input("  Select scale [1-5] (default 2=5K): ").strip()
    return [1_000, 5_000, 50_000, 500_000, 1_000_000][int(s) - 1] if s in "12345" else 5_000


def _menu() -> tuple[int, int]:
    print(MENU)
    choice = input("Select benchmark [1-7, 0]: ").strip()
    if choice not in "1234567":
        return 0, 0
    if choice == "0":
        return 0, 0
    scale = 5_000
    if choice in "1235":
        scale = _get_scale_interactive()
    return int(choice), scale


def _open_store(run_dir: Path) -> GlobalProjectionStore:
    store = GlobalProjectionStore(run_dir / "global.sqlite")
    store.open()
    return store


def _print_kv(k, v, w=30):
    print(f"  {k:<{w}} {v}")


def _format_result(mode: int, total: int, r: dict, json_out: bool) -> str:
    """Print a clean formatted summary for any benchmark mode."""
    lines = []
    sep = "─" * 60

    if json_out:
        return json.dumps(r, indent=2)

    lines.append(sep)
    if mode == 1:
        lines.append(
            f"  EXACT LOOKUP ACCURACY  │  {total:,} tools  │  {r.get('samples','')} queries"
        )
        lines.append(sep)
        lines.append(f"  Accuracy:        {r.get('accuracy',0):.2%}")
        lines.append(
            f"  Correct:         {r.get('correct',0)}  |  Misses: {r.get('misses',0)}  |  Incorrect: {r.get('incorrect',0)}"
        )
        lines.append(f"  Latency p50:     {r.get('latency_p50_ms',0):.3f} ms")
        lines.append(f"  Latency p95:     {r.get('latency_p95_ms',0):.3f} ms")
        lines.append(f"  Latency p99:     {r.get('latency_p99_ms',0):.3f} ms")
    elif mode == 2:
        lines.append(f"  TWO-STAGE DISCOVERY  │  {total:,} tools  │  {r.get('queries','')} queries")
        lines.append(sep)
        lines.append(f"  Precision@1:     {r.get('precision_at_1',0):.2%}")
        lines.append(f"  Precision@5:     {r.get('precision_at_5',0):.2%}")
        lines.append(
            f"  Ambiguous detect: {r.get('ambiguous_correctly_detected',0)}/{r.get('ambiguous_queries',0)} ({r.get('ambiguous_detection_rate',0):.0%})"
        )
        lines.append(f"  Stage1 p95:      {r.get('stage1_latency_p95_ms',0):.2f} ms")
    elif mode == 3:
        lines.append(
            f"  THREE-LANE ARCHITECTURE  │  {total:,} tools  │  {r.get('queries','')} queries"
        )
        lines.append(sep)
        lines.append(f"  Discovery recall@50:  {r.get('discovery_recall_at_50',0):.2%}")
        lines.append(f"  Resolver verdict acc:  {r.get('resolver_verdict_accuracy',0):.2%}")
        lines.append(
            f"  Authority FP rate:     {r.get('authority_false_positive_rate',0):.4%}  (must be 0)"
        )
    elif mode == 4:
        lines.append(f"  REQUESTFRAME EXTRACTION  │  {r.get('phrases','')} phrases")
        lines.append(sep)
        lines.append(f"  Operation:        {r.get('operation_accuracy',0):.1%}")
        lines.append(f"  Resource:         {r.get('resource_accuracy',0):.1%}")
        lines.append(f"  Connector:        {r.get('connector_accuracy',0):.1%}")
        lines.append(f"  All three:        {r.get('all_three_accuracy',0):.1%}")
    elif mode == 5:
        lines.append(
            f"  MANIFEST-AWARE DISCOVERY  │  {total:,} tools  │  {r.get('queries','')} queries"
        )
        lines.append(sep)
        lines.append(f"  Discovery recall@50:        {r.get('discovery_recall_at_50',0):.2%}")
        lines.append(f"  Resolver verdict acc:        {r.get('resolver_verdict_accuracy',0):.2%}")
        lines.append(
            f"  Authority FP rate:           {r.get('authority_false_positive_rate',0):.4%}  (must be 0)"
        )
        lines.append(f"  Novel-domain queries:        {r.get('novel_domain_queries',0)}")
        lines.append(f"  Novel-domain recall:         {r.get('novel_domain_recall',0):.2%}")
        lines.append(
            f"  Novel-domain verdict acc:    {r.get('novel_domain_verdict_accuracy',0):.2%}"
        )
        lines.append(f"  Natural-language queries:    {r.get('natural_language_queries',0)}")
        lines.append(f"  Natural-language recall:     {r.get('natural_language_recall',0):.2%}")
        lines.append(
            f"  Natural-language verdict:    {r.get('natural_language_verdict_accuracy',0):.2%}"
        )
    elif mode == 6:
        lines.append(f"  ALL BENCHMARKS  │  {total:,} tools")
        lines.append(sep)
        for name, key in [
            ("Exact Lookup", "exact_lookup"),
            ("Two-Stage", "two_stage"),
            ("Three-Lane", "three_lane"),
            ("Extraction", "extraction"),
            ("Manifest-Discovery", "manifest_discovery"),
        ]:
            sub = r.get(key, {})
            if key == "exact_lookup":
                lines.append(
                    f"  ── {name} ──  Accuracy: {sub.get('accuracy',0):.2%}  p95: {sub.get('latency_p95_ms',0):.3f}ms"
                )
            elif key == "two_stage":
                lines.append(
                    f"  ── {name} ──  P@1: {sub.get('precision_at_1',0):.2%}  p95: {sub.get('stage1_latency_p95_ms',0):.2f}ms"
                )
            elif key == "three_lane":
                lines.append(
                    f"  ── {name} ──  Recall: {sub.get('discovery_recall_at_50',0):.2%}  Verdict: {sub.get('resolver_verdict_accuracy',0):.2%}  AuthFP: {sub.get('authority_false_positive_rate',0):.4%}"
                )
            elif key == "extraction":
                lines.append(
                    f"  ── {name} ──  Op: {sub.get('operation_accuracy',0):.1%}  Resource: {sub.get('resource_accuracy',0):.1%}  All: {sub.get('all_three_accuracy',0):.1%}"
                )
            elif key == "manifest_discovery":
                lines.append(
                    f"  ── {name} ──  Recall: {sub.get('discovery_recall_at_50',0):.2%}  Verdict: {sub.get('resolver_verdict_accuracy',0):.2%}  Novel: {sub.get('novel_domain_recall',0):.2%}  Natural: {sub.get('natural_language_recall',0):.2%}"
                )
    lines.append(sep)
    return "\n".join(lines)


def _run_single(mode: int, scale: int, json_out: bool) -> dict:
    run_dir = (
        Path("data/back_tool_contract_bench")
        / f"mode{mode}_scale{scale}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    store = _open_store(run_dir)
    total = bootstrap_store(store, scale)
    result: dict = {"mode": mode, "scale": scale, "total_tools": total}

    try:
        if mode == 1:
            r = _bench1_exact_lookup(store, total)
            result["benchmark"] = "exact_lookup"
            result["results"] = r
        elif mode == 2:
            r = _bench2_discovery(store, total)
            result["benchmark"] = "two_stage_discovery"
            result["results"] = r
        elif mode == 3:
            r = _bench3_three_lane(store, total)
            result["benchmark"] = "three_lane"
            result["results"] = r
        elif mode == 4:
            r = _bench4_extraction()
            result["benchmark"] = "request_frame_extraction"
            result["results"] = r
        elif mode == 5:
            _build_manifest_tfidf_index(store)
            r = _bench5_manifest_discovery(store, total)
            result["benchmark"] = "manifest_aware_discovery"
            result["results"] = r
        elif mode == 6:
            b1 = _bench1_exact_lookup(store, total)
            _build_tfidf_index(store)
            b2 = _bench2_discovery(store, total)
            b3 = _bench3_three_lane(store, total)
            b4 = _bench4_extraction()
            _build_manifest_tfidf_index(store)
            b5 = _bench5_manifest_discovery(store, total)
            r = {
                "exact_lookup": b1,
                "two_stage": b2,
                "three_lane": b3,
                "extraction": b4,
                "manifest_discovery": b5,
            }
            result["results"] = r

        print(_format_result(mode, total, r, json_out))
        (run_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        return result
    finally:
        store.close()


def _run_scale_curve(mode: int, json_out: bool) -> dict:
    scales = [1_000, 5_000, 50_000, 500_000]
    curve = []
    header = f"\n{'='*60}\n  SCALE CURVE — Mode {mode}\n{'='*60}"
    print(header)
    for s in scales:
        r = _run_single(mode, s, True)
        print(_format_result(mode, r["total_tools"], r["results"], json_out))
        curve.append({"scale": s, **r.get("results", {})})
    print(f"{'='*60}")
    return {"mode": mode, "scale_curve": curve}


def main() -> int:
    args = _parse_cli()

    if args.benchmark:
        mode_map = {
            "exact": 1,
            "discovery": 2,
            "threelane": 3,
            "extraction": 4,
            "manifest": 5,
            "all": 6,
            "scale-curve": 7,
        }
        mode = mode_map.get(args.benchmark, 0)
        scale = SCALE_MAP.get(args.scale, 5_000)
        if mode == 0:
            print("Unknown benchmark.")
            return 1
        if mode == 7:
            _run_scale_curve(1, args.json)
            return 0
        _run_single(mode, scale, args.json)
        return 0

    # Interactive
    while True:
        mode, scale = _menu()
        if mode == 0:
            print("Goodbye.")
            return 0
        if mode == 7:
            print(
                "\n  Scale curve — which benchmark?\n   [1] Exact Lookup  [2] Two-Stage  [3] Three-Lane  [5] Manifest-Discovery"
            )
            sm = input("  Select [1-5]: ").strip()
            bm = int(sm) if sm in "1235" else 1
            _run_scale_curve(bm, False)
            continue
        _run_single(mode, scale, False)


def _parse_cli():
    p = argparse.ArgumentParser(description="Back Tool Contract Unified Benchmark")
    p.add_argument(
        "--benchmark",
        choices=[
            "exact",
            "discovery",
            "threelane",
            "extraction",
            "manifest",
            "all",
            "scale-curve",
        ],
    )
    p.add_argument("--scale", choices=["1k", "5k", "50k", "500k", "1m"], default="5k")
    p.add_argument("--json", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
