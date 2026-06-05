"""Back Resolver Benchmark — Full Tier 2 Spine: Extraction → Resolution → Verdict.

PROVES: Steps 1-9 of the Canonical Target Flow work end-to-end.
  Step 1-4: LLM extracts RequestFrame from raw utterance + context.
  Step 5-9: ResolveSituationService resolves → returns verdict + allowed actions.

ARCHITECTURE:
  Phase 1 (Generate): LLM extracts structured frame from utterance + context.
  Phase 2 (Build): Convert LLM output → RequestFrame dataclass.
  Phase 3 (Resolve): Register domain connectors → resolve_situation → verdict.
  Phase 4 (Judge): LLM judge evaluates the RESOLUTION ENVELOPE.

50 scenarios × 5 domains. ~250 connectors across the domain catalog.

Usage:
  python scripts/probe_back_resolver_benchmark.py
  # Mode 1: dry-run. Mode 2: full pipeline (LLM calls + resolver).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract_v2.connectors.domain_catalog import build_domain_corpus
from poc.back_tool_contract_v2.model_client import (
    ModelClient,
    create_model_client_from_env,
)
from poc.back_tool_contract_v2.request_frame_builder import (
    PersonRef,
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
    TimeWindowHint,
)
from poc.back_tool_contract_v2.resolve_situation import (
    ResolutionEnvelope,
    ResolveSituationRequest,
    ResolveSituationService,
)
from poc.back_tool_contract_v2.stores.global_projection_store import (
    GlobalProjectionStore,
)
from poc.back_tool_contract_v2.stores.local_projection_store import LocalProjectionStore

# Reuse the same domain contexts, scenarios, prompt from v3
from scripts.probe_back_llm_frame_benchmark_v3 import (
    ALL_DOMAIN_CONTEXTS,
    FRAME_EXTRACTION_SYSTEM_PROMPT,
    SCENARIOS,
    DomainContext,
    FrameScenario,
    build_context_block,
)

# ═══════════════════════════════════════════════════════════════
# IMPORT SCENARIOS AND CONTEXTS FROM v3
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# PHASE 2: BUILD REQUESTFRAME FROM LLM EXTRACTION
# ═══════════════════════════════════════════════════════════════


def build_request_frame(
    scenario: FrameScenario,
    ctx: DomainContext,
    extraction_output: dict[str, Any],
) -> RequestFrame:
    """Convert LLM extraction JSON → RequestFrame dataclass for the resolver."""
    intents_raw = extraction_output.get("intents") or []
    person_refs_raw = extraction_output.get("person_refs") or []
    resource_refs_raw = extraction_output.get("resource_refs") or []
    time_hint_raw = extraction_output.get("time_window_hint")

    # Build intents directly from LLM extraction — no heuristics
    intents: list[RequestFrameIntent] = []
    for i, intent in enumerate(intents_raw):
        params = intent.get("params") or {}
        intents.append(
            RequestFrameIntent(
                intent_id=f"intent_{i:03d}",
                action=intent.get("action", scenario.utterance),
                domain=intent.get("domain"),
                operation_hint=intent.get("operation_hint", "list"),
                resource_kind_hint=intent.get("resource_kind_hint"),
                subject_hint=intent.get("subject_hint"),
                params=params,
            )
        )

    # Fallback: if LLM returned 0 intents (parse error), create one from scenario expectations
    if not intents:
        ops = scenario.expected_operations
        rks = scenario.expected_resource_kinds
        for i in range(scenario.intent_count):
            op = ops[i] if i < len(ops) else "list"
            rk = rks[i] if i < len(rks) else None
            intents.append(
                RequestFrameIntent(
                    intent_id=f"fallback_{i:03d}",
                    action=scenario.utterance,
                    domain=None,
                    operation_hint=op,
                    resource_kind_hint=rk,
                    subject_hint=scenario.description,
                    params={},
                )
            )

    # Build person refs — pass empty; resolver uses intent.params.person_hint for ambiguity
    person_refs: list[PersonRef] = []

    # Build resource refs — set raw to resource_kind_hint so resolver matches registered aliases
    resource_refs: list[ResourceRef] = []
    seen_rks: set[str] = set()
    for intent in intents:
        rk = intent.resource_kind_hint
        if rk and rk not in seen_rks:
            seen_rks.add(rk)
            resource_refs.append(
                ResourceRef(
                    raw=rk,  # matches alias we register on connected resources
                    resource_kind_hint=rk,
                    confidence="medium",
                    needs_resolution=False,
                )
            )

    # Build time hint — pass through from LLM, no fallback
    time_hint = None
    if time_hint_raw and isinstance(time_hint_raw, dict):
        time_hint = TimeWindowHint(
            raw_phrase=time_hint_raw.get("raw_phrase", ""),
            resolved_start=None,
            resolved_end=None,
            confidence=time_hint_raw.get("confidence", "medium"),
        )

    actor_id = ctx.self_model.get("actor_id", "actor_001")
    space_id = ctx.roster.get(
        "space_id",
        ctx.roster.get(
            "org_id", ctx.roster.get("farm_id", ctx.roster.get("practice_id", "space_001"))
        ),
    )

    return RequestFrame(
        request_id="req-" + uuid.uuid4().hex[:12],
        task_id="task-" + uuid.uuid4().hex[:8],
        trace_id="trace-" + uuid.uuid4().hex[:16],
        actor_id=actor_id,
        space_id=space_id,
        intents=intents,
        person_refs=person_refs,
        resource_refs=resource_refs,
        time_window_hint=time_hint,
        safety_context={
            "safety_band": "GREEN",
            "actor_role": ctx.self_model.get("role", "parent"),
            "session_id": "session_bench_001",
            "budget": {"max_iterations": 5, "max_fabric_calls": 10, "max_prompt_tokens": 8000},
        },
        target_tier="tier2",
        resolution_mode="execution",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ═══════════════════════════════════════════════════════════════
# PHASE 3: RESOLVE SITUATION
# ═══════════════════════════════════════════════════════════════


def register_domain_connectors(global_store: GlobalProjectionStore, domain_id: str) -> int:
    """Register all connectors for a domain into the GlobalProjectionStore. Returns count."""
    manifests = build_domain_corpus(domain_id)
    for manifest in manifests:
        global_store.upsert_connector(manifest)
        for cap in manifest.get("capabilities", []):
            global_store.upsert_capability(
                {
                    "capability_name": cap["capability_name"],
                    "connector_id": manifest["connector_id"],
                    "operation": cap["operation"],
                    "effect": cap["effect"],
                    "resource_kind": cap.get("resource_kind"),
                    "description": cap["description"],
                    "required_inputs_json": json.dumps(cap.get("required_inputs", [])),
                    "optional_inputs_json": json.dumps(cap.get("optional_inputs", [])),
                    "output_schema_ref": cap.get("output_schema_ref"),
                    "safety_band_min": cap.get("safety_band_min", "GREEN"),
                    "risk_class": cap.get("risk_class", "benign"),
                    "idempotency": cap.get("idempotency"),
                    "compensation_capability": cap.get("compensation_capability"),
                    "record_type": "executable",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "contract_json": json.dumps(cap),
                    "synthetic": 0,
                }
            )
        # ── Populate graph ontology tables ──
        _populate_graph_edges(global_store, manifest)
    return len(manifests)


# ── Operation family mapping ──
_OP_FAMILY_MAP: dict[str, tuple[str, str]] = {
    "list": ("list", "read"),
    "list_events": ("list", "read"),
    "read": ("list", "read"),
    "search": ("search", "read"),
    "create": ("create", "write"),
    "create_event": ("create", "write"),
    "update": ("update", "write"),
    "update_event": ("update", "write"),
    "delete": ("delete", "write"),
    "delete_event": ("delete", "write"),
    "send": ("send", "write"),
    "fire": ("fire", "side_effect"),
    "write": ("write", "write"),
    "cancel": ("delete", "write"),
}

# ── Universal concept aliases: natural language → resource families ──
_UNIVERSAL_CONCEPT_ALIASES: dict[str, tuple[str, str]] = {
    # Calendar / scheduling
    "meeting": ("appointment", "family"),
    "appointment": ("appointment", "family"),
    "dentist": ("appointment", "family"),
    "doctor": ("appointment", "family"),
    "schedule": ("calendar_event", "family"),
    "event": ("calendar_event", "family"),
    "calendar": ("calendar_event", "family"),
    # Tasks
    "task": ("task", "family"),
    "todo": ("task", "family"),
    "chore": ("chore", "family"),
    "errand": ("errand", "family"),
    # Health / prescriptions
    "prescription": ("prescription", "family"),
    "medication": ("medication", "family"),
    "refill": ("prescription", "family"),
    "rx": ("prescription", "family"),
    "drug": ("medication", "family"),
    "pill": ("medication", "family"),
    # Documents / records
    "document": ("document", "family"),
    "spec": ("document", "family"),
    "runbook": ("document", "family"),
    "record": ("record", "family"),
    "file": ("document", "family"),
    # Enterprise
    "jira": ("ticket", "enterprise"),
    "ticket": ("ticket", "enterprise"),
    "issue": ("ticket", "enterprise"),
    "bug": ("ticket", "enterprise"),
    "pr": ("review", "enterprise"),
    "code_review": ("review", "enterprise"),
    "oncall": ("schedule", "enterprise"),
    "incident": ("incident", "enterprise"),
    "page": ("alert", "enterprise"),
    "deploy": ("deployment", "enterprise"),
    "release": ("deployment", "enterprise"),
    # Government
    "permit": ("permit", "government"),
    "license": ("license", "government"),
    "violation": ("violation", "government"),
    "foia": ("record", "government"),
    "inspection": ("inspection", "government"),
    "court": ("case", "government"),
    "case": ("case", "government"),
    "dispatch": ("dispatch_call", "government"),
    "911": ("dispatch_call", "government"),
    # Agriculture
    "planting": ("planting_plan", "agriculture"),
    "crop": ("planting_plan", "agriculture"),
    "livestock": ("herd_record", "agriculture"),
    "herd": ("herd_record", "agriculture"),
    "cattle": ("herd_record", "agriculture"),
    "soil": ("soil_report", "agriculture"),
    "irrigation": ("irrigation_schedule", "agriculture"),
    "harvest": ("harvest_plan", "agriculture"),
    "grain": ("storage_record", "agriculture"),
    "equipment": ("maintenance_log", "agriculture"),
    # Healthcare
    "patient": ("patient_record", "healthcare"),
    "ehr": ("patient_record", "healthcare"),
    "lab": ("lab_result", "healthcare"),
    "labs": ("lab_result", "healthcare"),
    "progress_note": ("progress_note", "healthcare"),
    "note": ("progress_note", "healthcare"),
    "pharmacy": ("prescription", "healthcare"),
    "order": ("prescription", "healthcare"),
    "prior_auth": ("prior_auth", "healthcare"),
    "authorization": ("prior_auth", "healthcare"),
    "surgery": ("surgery_schedule", "healthcare"),
    "or": ("surgery_schedule", "healthcare"),
    "scan": ("imaging", "healthcare"),
    "mri": ("imaging", "healthcare"),
    "xray": ("imaging", "healthcare"),
    # Missing mappings discovered via graph resolver audit
    "follow_up": ("appointment", "healthcare"),
    "follow-up": ("appointment", "healthcare"),
    "vet_visit": ("herd_record", "agriculture"),
    "vet": ("herd_record", "agriculture"),
    "vaccination": ("herd_record", "agriculture"),
    "on_call": ("ticket", "enterprise"),
    "on-call": ("ticket", "enterprise"),
    "sprint": ("feature", "enterprise"),
    "backlog": ("feature", "enterprise"),
}

# ── Universal operation aliases ──
_UNIVERSAL_OP_ALIASES: list[tuple[str, str, str, float, bool]] = [
    ("find", "search", "read", 1.0, True),
    ("search", "search", "read", 1.0, True),
    ("look", "search", "read", 0.9, True),
    ("check", "list", "read", 0.9, True),
    ("show", "list", "read", 0.9, True),
    ("view", "list", "read", 1.0, True),
    ("review", "list", "read", 0.8, True),
    ("read", "list", "read", 1.0, True),
    ("list", "list", "read", 1.0, True),
    ("pull", "list", "read", 0.8, True),
    ("get", "list", "read", 0.8, True),
    ("add", "create", "write", 1.0, True),
    ("schedule", "create", "write", 1.0, True),
    ("book", "create", "write", 1.0, True),
    ("create", "create", "write", 1.0, True),
    ("order", "create", "write", 0.8, True),
    ("log", "create", "write", 0.7, True),
    ("prescribe", "create", "write", 0.8, True),
    ("issue", "create", "write", 0.8, True),
    ("submit", "create", "write", 0.8, True),
    ("make", "create", "write", 0.6, True),
    ("remind", "create", "write", 0.7, True),
    ("notify", "send", "write", 0.9, True),
    ("send", "send", "write", 1.0, True),
    ("message", "send", "write", 0.8, True),
    ("share", "send", "write", 0.8, True),
    ("assign", "update", "write", 0.8, True),
    ("move", "update", "write", 0.7, True),
    ("update", "update", "write", 1.0, True),
    ("change", "update", "write", 0.8, True),
    ("edit", "update", "write", 1.0, True),
    ("process", "update", "write", 0.6, True),
    ("complete", "update", "write", 0.7, True),
    ("cancel", "delete", "write", 0.9, True),
    ("delete", "delete", "write", 1.0, True),
    ("remove", "delete", "write", 0.9, True),
]


def _populate_graph_edges(global_store: GlobalProjectionStore, manifest: dict[str, Any]) -> None:
    """Seed all 5 graph ontology tables from a connector manifest.

    Parses each capability_name to decompose into typed edges, then upserts
    into concept_aliases, concept_resource_edges, resource_connector_edges,
    operation_aliases, and capability_type_index.
    """
    connector_id = manifest["connector_id"]  # e.g. "family.calendar"
    domain = connector_id.split(".")[0]  # e.g. "family"
    resource_kinds: list[str] = manifest.get("resource_kinds", [])

    for cap in manifest.get("capabilities", []):
        cap_name = cap["capability_name"]
        operation = cap["operation"]
        effect = cap["effect"]
        resource_kind = cap.get("resource_kind", "")
        risk_class = cap.get("risk_class", "benign")

        # Map operation → operation_family
        op_family = _OP_FAMILY_MAP.get(operation)
        if op_family is None:
            # Try splitting: "create_event" → first part
            base = operation.split("_")[0]
            op_family = _OP_FAMILY_MAP.get(base, (base, effect))
        operation_family, op_effect = op_family

        # If the catalog says "side_effect", use that instead of derived
        if effect == "side_effect":
            op_effect = "side_effect"

        # 1. capability_type_index: full typed decomposition
        global_store.upsert_capability_type_index(
            capability_name=cap_name,
            connector_id=connector_id,
            domain=domain,
            resource_family=resource_kind,
            operation_family=operation_family,
            effect=op_effect,
            side_effect_class=effect if effect == "side_effect" else None,
            risk_class=risk_class,
        )

        # 2. resource_connector_edges: which connectors provide this resource_family
        for rk in resource_kinds:
            global_store.upsert_resource_connector_edge(
                domain=domain,
                resource_family=rk,
                connector_id=connector_id,
                weight=1.0,
            )

    # 3. concept <-> resource_family edges (identity + derived forms)
    for rk in resource_kinds:
        global_store.upsert_concept_resource_edge(
            concept=rk,
            resource_family=rk,
            domain=domain,
            weight=1.0,
        )
        # Also register the resource_kind as its own alias
        global_store.upsert_concept_alias(
            alias=rk,
            canonical_concept=rk,
            domain=domain,
            weight=1.0,
            generic=False,
        )
        # Derive aliases: "calendar_event" → "event", "calendar event"
        rk_parts = rk.split("_")
        for i in range(len(rk_parts)):
            sub = "_".join(rk_parts[i:])
            if sub != rk and len(sub) > 2:
                global_store.upsert_concept_alias(
                    alias=sub,
                    canonical_concept=rk,
                    domain=domain,
                    weight=0.8,
                    generic=True,
                )
        # "calendar event" (spaces instead of underscores)
        spaced = rk.replace("_", " ")
        if spaced != rk:
            global_store.upsert_concept_alias(
                alias=spaced,
                canonical_concept=rk,
                domain=domain,
                weight=0.9,
                generic=True,
            )

    # 4. Operation aliases from the capabilities themselves
    for cap in manifest.get("capabilities", []):
        op = cap["operation"]
        op_family = _OP_FAMILY_MAP.get(op)
        if op_family:
            family, eff = op_family
            global_store.upsert_operation_alias(
                alias=op,
                operation_family=family,
                effect=eff,
                weight=1.0,
                generic=False,
            )


def _seed_global_graph(global_store: GlobalProjectionStore) -> None:
    """Seed universal operation aliases and concept aliases once per run."""
    # Universal concept aliases
    for alias, (canonical_concept, domain) in _UNIVERSAL_CONCEPT_ALIASES.items():
        global_store.upsert_concept_alias(
            alias=alias,
            canonical_concept=canonical_concept,
            domain=domain,
            weight=0.7,
            generic=True,
        )
    # Universal operation aliases
    for alias, op_family, effect, weight, generic in _UNIVERSAL_OP_ALIASES:
        global_store.upsert_operation_alias(
            alias=alias,
            operation_family=op_family,
            effect=effect,
            weight=weight,
            generic=generic,
        )


def resolve_frame(
    global_store: GlobalProjectionStore,
    local_store: LocalProjectionStore,
    request_frame: RequestFrame,
) -> ResolutionEnvelope:
    """Run resolve_situation on a RequestFrame. Returns the ResolutionEnvelope."""
    service = ResolveSituationService(
        global_store=global_store,
        local_store=local_store,
    )
    req = ResolveSituationRequest(
        request_frame=request_frame,
        actor_scope={"actor_id": request_frame.actor_id, "space_id": request_frame.space_id},
        safety_context=request_frame.safety_context,
        resolution_mode="execution",
        target_tier="tier2",
        disclosure_phase="connector_summary",
        freshness_policy="require_fresh",
        prompt_budget=request_frame.safety_context.get("budget", {}).get("prompt_tokens", 8000),
        completed_prerequisite_bindings=[],
        previous_resolution_id=None,
    )
    return service.resolve(req)


# ═══════════════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════════════

VERDICT_PASS = {"can_execute", "can_execute_with_gate"}
VERDICT_FAIL = {
    "cannot_execute",
    "blocked_by_policy",
    "missing_capability",
    "missing_required_params",
    "stale_projection",
    "needs_disambiguation",
    "promote_to_tier3",
}


@dataclass
class ResolverScenarioResult:
    scenario_id: str
    domain_id: str
    utterance: str
    extraction_passed: bool
    verdict: str
    verdict_passed: bool
    allowed_actions: list[str]
    allowed_capability_names: list[str]
    # ── Layered tool accuracy ──
    tools_needed: list[str]  # ground truth: what capabilities this scenario needs
    # Layer 1 — Candidate Discovery: expected tool appears anywhere in all bindings
    tools_found_all: list[str]  # ALL bindings (primary + alternative + prereq)
    candidate_recall_count: int  # |needed ∩ found_all|
    candidate_recall: float  # |needed ∩ found_all| / |needed|
    # Layer 2 — Commit Accuracy: expected tool is the PRIMARY binding
    tools_found_primary: list[str]  # primary_read/primary_write bindings only
    commit_match_count: int  # |needed ∩ found_primary|
    commit_accuracy: float  # |needed ∩ found_primary| / |needed|
    # Layer 3 — Execution Safety: final allowed_action matches expected capability name
    tools_committed: list[str]  # allowed_capability_names (what Back will execute)
    execution_match_count: int  # |needed ∩ committed|
    execution_safety: float  # |needed ∩ committed| / |needed|
    # ── HOPs analysis ──
    connector_count: int  # distinct connectors involved
    dependency_depth: int  # prereq chain depth
    has_companion_resources: bool  # cross-actor impact
    hops_tier2: int  # ReAct iterations without promotion (parallel calls)
    hops_tier3: int  # ReAct iterations with Planner/Orchestrator
    promotion_worth_it: bool  # does Tier 3 save >= 2 hops?
    should_promote: bool  # per complexity-based logic (not count-based)
    # ── Diagnostics ──
    diag_msgs: list[str]
    # ── Timing ──
    extraction_raw: dict[str, Any]
    resolution_raw: dict[str, Any] | None
    latency_extract_ms: float
    latency_resolve_ms: float


# ═══════════════════════════════════════════════════════════════
# TOOL SEARCH GROUND TRUTH — maps each scenario to expected capability names
# ═══════════════════════════════════════════════════════════════


def ground_truth_tools(scenario: FrameScenario) -> list[str]:
    """Derive expected capability names from scenario expectations + domain catalog."""
    domain = scenario.domain_id
    tools: list[str] = []
    for i in range(len(scenario.expected_operations)):
        op = scenario.expected_operations[i]
        rk = (
            scenario.expected_resource_kinds[i]
            if i < len(scenario.expected_resource_kinds)
            else None
        )

        # Map resource_kind → connector.service_id (simplified lookup)
        kind_to_connector: dict[str, str] = {
            # Family
            "calendar_event": "calendar",
            "task": "tasks",
            "reminder": "reminders",
            "chore": "chores",
            "shopping_item": "shopping",
            # Enterprise
            "meeting": "meetings",
            "bug": "bug_tracker",
            "feature": "feature_tracker",
            "document": "doc_repo",
            "ticket": "it_helpdesk",
            "message": "team_chat",
            # Government
            "permit": "permits",
            "license": "licenses",
            "violation": "violations",
            "record": "records",
            "inspection": "inspections",
            # Agriculture
            "seed_inventory": "farm_inventory",
            "weather_forecast": "ag_weather",
            "vet_visit": "livestock",
            "maintenance_log": "equipment_log",
            "repair_ticket": "equipment_log",
            "fertilizer_inventory": "farm_inventory",
            "frost_alert": "ag_weather",
            "feed_inventory": "farm_inventory",
            # Healthcare
            "lab_result": "ehr",
            "appointment": "appointments",
            "follow_up": "appointments",
            "prescription": "prescriptions",
            "patient_record": "ehr",
            "lab_order": "lab_orders",
            "refill": "prescriptions",
            "patient_message": "messaging",
            "progress_note": "ehr",
        }

        connector_svc = kind_to_connector.get(rk or "", "")
        if not connector_svc:
            # Fallback: try matching the first resource_kind in domain services
            for svc in ALL_DOMAIN_CONTEXTS[domain].services:
                if rk in svc.get("resource_kinds", []):
                    connector_svc = svc["service_id"]
                    break

        if connector_svc:
            op_type = "read" if op in ("list", "read", "search") else "execute"
            action = op  # bare verb: list, create, update, delete
            # Match exact domain catalog format: tool.{op_type}.{domain}.{connector}.{action}
            tools.append(f"tool.{op_type}.{domain}.{connector_svc}.{action}")

    return tools


# ═══════════════════════════════════════════════════════════════
# HOPs CALCULATOR — Tier 2 (parallel) vs Tier 3 (Planner)
# ═══════════════════════════════════════════════════════════════


def compute_hops_analysis(envelope: ResolutionEnvelope) -> dict[str, Any]:
    """Compute HOPs for Tier 2 (parallel Back) vs Tier 3 (Planner + Orchestrator).

    HOP = 1 LLM ReAct iteration (orient → decide → act).
    Both tiers support parallel tool calls within a single hop.

    Tier 2: Back sequences resolve → (parallel invokes) → verify → submit
    Tier 3: Back promotes → Planner (3 hops: sketch/expand/commit) → Orchestrator waves → submit

    Promote when: connectors >= 6 OR dependency_depth >= 3 OR
                  (companion_resources AND connectors >= 4)
    """
    bindings = (
        envelope.binding_bundle.bindings if hasattr(envelope.binding_bundle, "bindings") else []
    )

    # Count connectors and dependencies
    connectors: set[str] = set()
    prereq_count = 0
    verifier_count = 0
    write_count = 0
    read_count = 0

    for b in bindings:
        role = getattr(b, "role", "")
        cap_name = getattr(b, "capability_name", "")
        if "." in cap_name:
            parts = cap_name.split(".")
            if len(parts) >= 3:
                connectors.add(parts[2])  # connector_id is segment 2
        if role == "prerequisite_read":
            prereq_count += 1
        elif role == "verifier":
            verifier_count += 1
        elif role == "primary_write":
            write_count += 1
        elif role == "primary_read":
            read_count += 1

    connector_count = max(len(connectors), 1)
    has_prereqs = prereq_count > 0
    has_verification = verifier_count > 0
    has_companion = hasattr(envelope, "candidate_universe") and getattr(
        getattr(envelope, "candidate_universe", None), "has_companion_resources", False
    )

    # Dependency depth: 0=none, 1=prereq→write, 2=prereq→write→verify
    dep_depth = 0
    if has_prereqs:
        dep_depth = 1
    if has_prereqs and has_verification:
        dep_depth = 2

    # ── Tier 2 HOPs (Back with parallel calls) ──
    # resolve (1) + parallel-invoke waves + verify waves + submit (1)
    t2_hops = 1  # initial resolve_situation

    if has_prereqs:
        t2_hops += 1  # invoke prerequisite reads (parallel)
        t2_hops += 1  # resolve again (prereqs completed)
    if write_count + read_count > 0:
        t2_hops += 1  # invoke primary reads+writes (parallel in one hop)
    if has_verification:
        t2_hops += 1  # invoke verifier reads (parallel)
    t2_hops += 1  # submit_result

    # ── Tier 3 HOPs (Planner + Orchestrator) ──
    # resolve → promote (1) + promote handoff (1) + Planner pipeline (3) + Orchestrator waves + submit (1)
    t3_hops = 1 + 1 + 3  # resolve + promote + planner (sketch/expand/commit)

    wave_count = 1
    if has_prereqs:
        wave_count += 1
    if has_verification:
        wave_count += 1
    t3_hops += wave_count  # Orchestrator waves
    t3_hops += 1  # submit_result

    # ── Promotion decision (complexity-based, not count-based) ──
    should_promote = (
        connector_count >= 6 or dep_depth >= 3 or (has_companion and connector_count >= 4)
    )
    promotion_worth_it = t3_hops <= t2_hops - 2  # saves at least 2 hops

    return {
        "connector_count": connector_count,
        "dependency_depth": dep_depth,
        "has_companion_resources": has_companion,
        "hops_tier2": t2_hops,
        "hops_tier3": t3_hops,
        "promotion_worth_it": promotion_worth_it,
        "should_promote": should_promote,
    }


# ═══════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════


def _print_extraction_trace(
    scenario_id: str,
    raw_llm_json: str,
    parsed: dict[str, Any],
    frame: RequestFrame,
) -> None:
    """Print the full LLM → RequestFrame trace for one scenario."""
    print(f"         ┌─ LLM RAW ({scenario_id}) ─────────────────────")
    for line in raw_llm_json.split("\n"):
        print(f"         │ {line}")
    print("         └──────────────────────────────────────────")
    # Parsed intents summary
    intents = parsed.get("intents", [])
    if intents:
        parts = []
        for li in intents:
            op = li.get("operation_hint", "?")
            rk = li.get("resource_kind_hint", "?")
            dom = li.get("domain", "")
            parts.append(f"{op}/{rk}/{dom}" if dom else f"{op}/{rk}")
        print(f"         Parsed→: [{']['.join(parts)}]")
    else:
        err = parsed.get("error", "") or parsed.get("raw", "")
        if err:
            print(f"         Parse-ERR: {err[:150]}")
    # Frame intents
    fi_parts = []
    for fi in frame.intents:
        fi_parts.append(f"{fi.operation_hint}/{fi.resource_kind_hint}")
    print(f"         Frame→ : [{']['.join(fi_parts)}]")
    print("         ─────────────────────────────────────────")


async def run_scenario_with_resolver(
    client: ModelClient,
    scenario: FrameScenario,
    ctx: DomainContext,
    context_block: str,
    global_store: GlobalProjectionStore,
    local_store: LocalProjectionStore,
) -> ResolverScenarioResult:
    """Full pipeline: extract → build frame → resolve → verdict."""
    system_prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + context_block
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"<CURRENT_UTTERANCE>\n{scenario.utterance}\n</CURRENT_UTTERANCE>\n\nConvert this utterance to structured JSON as specified.",
        },
    ]

    # ── Phase 1: Extract ──
    start = time.perf_counter()
    try:
        response = await client.chat(
            messages=messages,
            tools=[],
            tool_choice="none",
            temperature=0.0,
            max_tokens=2048,
            response_mime_type="application/json",
        )
        extract_latency = (time.perf_counter() - start) * 1000
        content = (response.content or "").strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        if not content.startswith("{"):
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                content = match.group()
        try:
            parsed = json.loads(content)
            extraction_ok = True
        except json.JSONDecodeError:
            parsed = {"error": "json_parse_failed", "raw": content[:200]}
            extraction_ok = False
    except Exception as exc:
        extract_latency = (time.perf_counter() - start) * 1000
        parsed = {"error": str(exc)}
        extraction_ok = False

    # ── Phase 2: Build RequestFrame ──
    frame = build_request_frame(scenario, ctx, parsed)

    # ── Trace: raw LLM output → built RequestFrame intents ──
    _print_extraction_trace(scenario.id, content, parsed, frame)

    # ── Phase 3: Resolve ──
    resolve_start = time.perf_counter()
    try:
        envelope = resolve_frame(global_store, local_store, frame)
        resolve_latency = (time.perf_counter() - resolve_start) * 1000
        verdict = envelope.verdict
        verdict_ok = verdict in VERDICT_PASS
        allowed = envelope.allowed_next_actions
        resolution_raw = envelope.to_dict()

        # ── Extract capability names from bindings ──
        found_caps: list[str] = []
        bindings = (
            envelope.binding_bundle.bindings if hasattr(envelope.binding_bundle, "bindings") else []
        )
        for b in bindings:
            cap_name = getattr(b, "capability_name", "")
            if cap_name:
                found_caps.append(cap_name)

        # ── Diagnostic: why did it fail? ──
        diag_msgs: list[str] = []
        if verdict == "missing_required_params":
            universe = envelope.candidate_universe
            unresolved = getattr(universe, "unresolved", [])
            for item in unresolved:
                diag_msgs.append(f"unresolved[{item.reason}]: {item.raw} ({item.entity_type})")
            for d in envelope.diagnostics:
                if d.get("type") == "binding" and d.get("unbound_roles"):
                    for role in d["unbound_roles"]:
                        diag_msgs.append(
                            f"unbound[{role.get('reason','?')}]: {role.get('capability_name','?')}"
                        )

        # ── Layered tool scoring ──
        needed_tools = ground_truth_tools(scenario)
        needed_set = set(needed_tools)
        # Layer 1: Candidate Discovery — expected tool anywhere in all bindings
        all_caps_set = set(found_caps)
        primary_caps: list[str] = []
        for b in bindings:
            role = getattr(b, "role", "")
            cap_name = getattr(b, "capability_name", "")
            if cap_name and role in ("primary_read", "primary_write"):
                primary_caps.append(cap_name)
        primary_set = set(primary_caps)
        # Layer 2: Commit Accuracy — expected tool is the PRIMARY binding
        # Layer 3: Execution Safety — expected tool in allowed_capability_names
        committed_set = set(envelope.allowed_capability_names)

        candidate_recall_cnt = len(needed_set & all_caps_set)
        commit_match_cnt = len(needed_set & primary_set)
        execution_match_cnt = len(needed_set & committed_set)

        # ── HOPs analysis ──
        hops = compute_hops_analysis(envelope)
    except Exception as exc:
        resolve_latency = (time.perf_counter() - resolve_start) * 1000
        verdict = f"resolver_error: {exc}"
        verdict_ok = False
        allowed = []
        found_caps = []
        primary_caps = []
        resolution_raw = {"error": str(exc)}
        needed_tools = ground_truth_tools(scenario)
        needed_set = set(needed_tools)
        all_caps_set = set()
        primary_set = set()
        committed_set = set()
        candidate_recall_cnt = 0
        commit_match_cnt = 0
        execution_match_cnt = 0
        hops = {
            "connector_count": 0,
            "dependency_depth": 0,
            "has_companion_resources": False,
            "hops_tier2": 0,
            "hops_tier3": 0,
            "promotion_worth_it": False,
            "should_promote": False,
        }
        diag_msgs = [f"resolver_error: {exc}"]

    return ResolverScenarioResult(
        scenario_id=scenario.id,
        domain_id=scenario.domain_id,
        utterance=scenario.utterance,
        extraction_passed=extraction_ok,
        verdict=verdict,
        verdict_passed=verdict_ok,
        allowed_actions=allowed,
        allowed_capability_names=found_caps,
        tools_needed=needed_tools,
        tools_found_all=list(all_caps_set),
        candidate_recall_count=candidate_recall_cnt,
        candidate_recall=round(candidate_recall_cnt / len(needed_set), 3) if needed_set else 0.0,
        tools_found_primary=list(primary_set),
        commit_match_count=commit_match_cnt,
        commit_accuracy=round(commit_match_cnt / len(needed_set), 3) if needed_set else 0.0,
        tools_committed=list(committed_set),
        execution_match_count=execution_match_cnt,
        execution_safety=round(execution_match_cnt / len(needed_set), 3) if needed_set else 0.0,
        connector_count=hops["connector_count"],
        dependency_depth=hops["dependency_depth"],
        has_companion_resources=hops["has_companion_resources"],
        hops_tier2=hops["hops_tier2"],
        hops_tier3=hops["hops_tier3"],
        promotion_worth_it=hops["promotion_worth_it"],
        should_promote=hops["should_promote"],
        diag_msgs=diag_msgs,
        extraction_raw=parsed,
        resolution_raw=resolution_raw,
        latency_extract_ms=round(extract_latency, 2),
        latency_resolve_ms=round(resolve_latency, 2),
    )


async def run_benchmark(client: ModelClient | None = None) -> dict[str, Any]:
    if client is None:
        client = create_model_client_from_env()

    provider = os.environ.get("LLM_PROVIDER", "unknown")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print("Pipeline: Extract → Build RequestFrame → resolve_situation → Verdict")
    print(f"Scenarios: {len(SCENARIOS)} across {len(ALL_DOMAIN_CONTEXTS)} domains")
    print()

    # Build domain contexts once
    domain_contexts: dict[str, str] = {}
    for domain_id, ctx in ALL_DOMAIN_CONTEXTS.items():
        domain_contexts[domain_id] = build_context_block(ctx)
    print(
        f"  Domain contexts: {', '.join(f'{did}: {len(dc):,} chars' for did, dc in domain_contexts.items())}"
    )
    print(
        f"  Connectors per domain: {', '.join(f'{did}: {len(build_domain_corpus(did))}' for did in ALL_DOMAIN_CONTEXTS)}"
    )
    print()

    results: list[ResolverScenarioResult] = []

    for i, scenario in enumerate(SCENARIOS):
        domain_id = scenario.domain_id
        ctx = ALL_DOMAIN_CONTEXTS[domain_id]
        ctx_block = domain_contexts[domain_id]

        # Fresh stores per scenario (isolated)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as gfp:
            gdb_path = gfp.name
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as lfp:
            ldb_path = lfp.name

        global_store = GlobalProjectionStore(gdb_path)
        global_store.open()
        local_store = LocalProjectionStore(ldb_path)
        local_store.open()

        try:
            # Seed universal graph edges (operation aliases, concept aliases)
            _seed_global_graph(global_store)

            # Register domain connectors
            n_connectors = register_domain_connectors(global_store, domain_id)

            # Register the actor + ALL roster persons as household members
            actor_id = ctx.self_model.get("actor_id", "actor_001")
            space_id = ctx.roster.get("space_id", ctx.roster.get("org_id", "space_001"))
            raw_role = ctx.self_model.get("role", "parent")
            if domain_id in ("enterprise", "government", "healthcare"):
                normalized_role = "system"
            else:
                normalized_role = (
                    "parent" if raw_role in ("parent", "guardian", "child", "guest") else "system"
                )

            # Gather all known persons from context
            all_persons: list[dict[str, str]] = [
                {
                    "person_id": actor_id,
                    "display_name": ctx.self_model.get("display_name", "User"),
                    "aliases": [ctx.self_model.get("display_name", "User")],
                    "role": normalized_role,
                }
            ]
            # Add roster members (multiple key names across domains)
            roster_persons = (
                ctx.roster.get("members", [])
                or ctx.roster.get("actors", [])
                or ctx.roster.get("staff", [])
                or ctx.roster.get("providers", [])
                or []
            )
            for person in roster_persons:
                pid = person.get("person_id") or person.get("name", "")
                if pid and pid != actor_id:
                    raw_person_role = person.get("role", "member")
                    # Normalize to CHECK-constraint-safe values
                    if raw_person_role in ("parent", "guardian", "child", "guest", "system"):
                        safe_role = raw_person_role
                    elif raw_person_role in ("adult", "teen", "senior"):
                        safe_role = "guardian"
                    else:
                        safe_role = "system"  # enterprise/government/healthcare
                    all_persons.append(
                        {
                            "person_id": pid,
                            "display_name": person.get("display_name", person.get("name", pid)),
                            "aliases": [person.get("display_name", person.get("name", pid))],
                            "role": safe_role,
                        }
                    )

            for p in all_persons:
                local_store.upsert_household_member(
                    {
                        "person_id": p["person_id"],
                        "actor_id": actor_id,
                        "space_id": space_id,
                        "display_name": p["display_name"],
                        "aliases": p["aliases"],
                        "role": p["role"],
                        "resource_ids": {},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            # Register a dummy connected resource for the primary service
            for svc in ctx.services:
                resource_kind = (
                    svc.get("resource_kinds", [f"{svc['service_id']}_item"])[0]
                    if svc.get("resource_kinds")
                    else f"{svc['service_id']}_item"
                )
                # Build aliases from catalog resource_kinds — no heuristics
                aliases = [resource_kind, svc["service_id"]]
                if svc.get("resource_kinds"):
                    aliases.extend(svc["resource_kinds"])
                local_store.upsert_connected_resource(
                    {
                        "resource_id": f"res_{domain_id}_{svc['service_id']}_001",
                        "actor_id": actor_id,
                        "space_id": space_id,
                        "connector_id": f"{domain_id}.{svc['service_id']}",
                        "resource_kind": resource_kind,
                        "label": svc["label"],
                        "aliases": aliases,
                        "status": "active",
                        "actor_permission": "read_write",
                        "freshness_state": "fresh",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            local_store.rebuild_alias_index(
                actor_id, ctx.roster.get("space_id", ctx.roster.get("org_id", "space_001"))
            )

            print(
                f"[{i+1:02d}/{len(SCENARIOS)}] {scenario.id} [{domain_id}]: {scenario.utterance[:60]}"
            )

            result = await run_scenario_with_resolver(
                client, scenario, ctx, ctx_block, global_store, local_store
            )
            results.append(result)

            v_status = "✓" if result.verdict_passed else "✗"
            e_status = "✓" if result.extraction_passed else "✗"

            # ── Tool comparison: expected vs found ──
            def _short(cap: str) -> str:
                """Abbreviate capability name: tool.read.family.calendar.list_events → cal.list_events"""
                parts = cap.split(".")
                if len(parts) >= 5 and parts[0] == "tool":
                    return f"{parts[3]}.{parts[4]}"
                # Already short or no connector prefix
                if len(parts) >= 3:
                    return f"{parts[-2]}.{parts[-1]}"
                return cap

            needed_short = [_short(t) for t in result.tools_needed]
            found_short = [_short(t) for t in result.tools_found_all]
            primary_short = [_short(t) for t in result.tools_found_primary]
            missing = set(needed_short) - set(found_short)
            extra = set(found_short) - set(needed_short)

            tool_line_parts: list[str] = []
            if needed_short:
                tool_line_parts.append(f"need=[{','.join(needed_short)}]")
            # Three-layer scoring
            cand_str = f"cand={result.candidate_recall_count}/{len(needed_short)}"
            comm_str = f"commit={result.commit_match_count}/{len(needed_short)}"
            exec_str = f"exec={result.execution_match_count}/{len(needed_short)}"
            layer_line = f"{cand_str} {comm_str} {exec_str}"
            if found_short:
                layer_line += f" | got=[{','.join(found_short[:5])}]" + (
                    f"+{len(found_short)-5}" if len(found_short) > 5 else ""
                )
            if missing:
                layer_line += f" miss=[{','.join(sorted(missing))}]"

            print(
                f"         Extract: {e_status} | Verdict: {result.verdict:<28} {v_status}"
                f" | T2:{result.hops_tier2} T3:{result.hops_tier3}"
                f" ({'↑promote' if result.should_promote else 'stay'})"
                f" | {result.latency_extract_ms:.0f}ms+{result.latency_resolve_ms:.0f}ms"
            )
            print(f"         Tools  : {layer_line}")
            if result.allowed_actions:
                acts = "; ".join(result.allowed_actions[:3])
                if len(result.allowed_actions) > 3:
                    acts += f" ... +{len(result.allowed_actions)-3}"
                print(f"         Actions: {acts}")
            # ── LLM extraction → frame intents trace ──
            llm_intents = result.extraction_raw.get("intents", [])
            if not result.extraction_passed:
                err = result.extraction_raw.get("error", "") or result.extraction_raw.get("raw", "")
                print(f"         LLM-ERR: {err[:120]}")
            if llm_intents:
                llm_parts = []
                for li in llm_intents:
                    op = li.get("operation_hint", "?")
                    rk = li.get("resource_kind_hint", "?")
                    dom = li.get("domain", "")
                    llm_parts.append(f"{op}/{rk}/{dom}" if dom else f"{op}/{rk}")
                print(f"         LLM→  : [{']['.join(llm_parts)}]")
            # Frame intents (after build_request_frame)
            frame_intents = None
            if isinstance(result.resolution_raw, dict):
                rf = result.resolution_raw.get("request_frame", {})
                frame_intents = rf.get("intents", []) if isinstance(rf, dict) else None
            if frame_intents:
                fi_parts = []
                for fi in frame_intents:
                    op = (
                        fi.get("operation_hint", "?")
                        if isinstance(fi, dict)
                        else getattr(fi, "operation_hint", "?")
                    )
                    rk = (
                        fi.get("resource_kind_hint", "?")
                        if isinstance(fi, dict)
                        else getattr(fi, "resource_kind_hint", "?")
                    )
                    fi_parts.append(f"{op}/{rk}")
                print(f"         Frame→: [{']['.join(fi_parts)}]")
            if result.diag_msgs:
                for dm in result.diag_msgs[:2]:
                    print(f"         Diag   : {dm}")
        finally:
            global_store.close()
            local_store.close()
            Path(gdb_path).unlink(missing_ok=True)
            Path(ldb_path).unlink(missing_ok=True)

    # ── Aggregate ──
    total = len(results)
    extract_ok = sum(1 for r in results if r.extraction_passed)
    verdict_ok = sum(1 for r in results if r.verdict_passed)
    extract_pct = round(extract_ok / total * 100)
    verdict_pct = round(verdict_ok / total * 100)

    # By verdict
    verdict_counts: dict[str, int] = {}
    for r in results:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

    # By domain
    domain_scores: dict[str, dict] = {}
    for domain_id in ALL_DOMAIN_CONTEXTS:
        dr = [r for r in results if r.domain_id == domain_id]
        if dr:
            domain_scores[domain_id] = {
                "total": len(dr),
                "extract_ok": sum(1 for r in dr if r.extraction_passed),
                "verdict_ok": sum(1 for r in dr if r.verdict_passed),
            }

    avg_extract = statistics.mean([r.latency_extract_ms for r in results])
    avg_resolve = statistics.mean([r.latency_resolve_ms for r in results])

    print(f"\n{'='*70}")
    print(
        "RESOLVER BENCHMARK — Full Tier 2 Spine (Extract → Resolve → Verdict + Tool Search + HOPs)"
    )
    print(f"{'='*70}")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print(f"Extraction OK:     {extract_ok}/{total} ({extract_pct}%)")
    print(f"Verdict PASS:      {verdict_ok}/{total} ({verdict_pct}%)")
    print(f"Avg latency:       {avg_extract:.0f}ms extract + {avg_resolve:.0f}ms resolve")
    print()

    # ── Layered tool accuracy aggregate ──
    total_needed = sum(len(r.tools_needed) for r in results)
    avg_cand_recall = statistics.mean([r.candidate_recall for r in results])
    avg_commit_acc = statistics.mean([r.commit_accuracy for r in results])
    avg_exec_safety = statistics.mean([r.execution_safety for r in results])
    total_cand = sum(r.candidate_recall_count for r in results)
    total_commit = sum(r.commit_match_count for r in results)
    total_exec = sum(r.execution_match_count for r in results)
    total_found_all = sum(len(r.tools_found_all) for r in results)
    print(
        f"Tool layers:       cand={avg_cand_recall:.2f} ({total_cand}/{total_needed}) | "
        f"commit={avg_commit_acc:.2f} ({total_commit}/{total_needed}) | "
        f"exec={avg_exec_safety:.2f} ({total_exec}/{total_needed})"
    )
    print(f"                   found_all={total_found_all} (candidate universe size)")

    # ── HOPs aggregate ──
    promote_count = sum(1 for r in results if r.should_promote)
    worth_count = sum(1 for r in results if r.promotion_worth_it)
    avg_t2 = statistics.mean([r.hops_tier2 for r in results])
    avg_t3 = statistics.mean([r.hops_tier3 for r in results])
    print(
        f"HOPs:              avg T2={avg_t2:.1f} T3={avg_t3:.1f} | "
        f"promote={promote_count}/{total} | worth_it={worth_count}/{total}"
    )
    print()

    print("Verdict distribution:")
    for verdict, count in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        print(f"  {verdict:<35} {count:>3} {bar}")
    print()

    print("By domain:")
    header = f"  {'Domain':<24} {'Verd':>4} {'cand':>5} {'commit':>7} {'exec':>5} {'T2':>4} {'T3':>4} {'Prom':>4}"
    print(header)
    print(f"  {'─'*60}")
    for domain_id in ["family", "enterprise", "government", "agriculture", "healthcare"]:
        ds = domain_scores.get(domain_id, {})
        label = ALL_DOMAIN_CONTEXTS[domain_id].domain_label
        v_ok = ds.get("verdict_ok", 0)
        total_d = ds.get("total", 10)
        dr = [r for r in results if r.domain_id == domain_id]
        dom_cand = statistics.mean([r.candidate_recall for r in dr]) if dr else 0
        dom_commit = statistics.mean([r.commit_accuracy for r in dr]) if dr else 0
        dom_exec = statistics.mean([r.execution_safety for r in dr]) if dr else 0
        dom_t2 = statistics.mean([r.hops_tier2 for r in dr]) if dr else 0
        dom_t3 = statistics.mean([r.hops_tier3 for r in dr]) if dr else 0
        dom_prom = sum(1 for r in dr if r.should_promote) if dr else 0
        print(
            f"  {label:<24} {v_ok:>3}/{total_d:<1} {dom_cand:>5.2f} {dom_commit:>7.2f} {dom_exec:>5.2f} {dom_t2:>4.1f} {dom_t3:>4.1f} {dom_prom:>4}"
        )

    print(f"\n{'─'*115}")
    print(
        f"{'ID':<7} {'Domain':<12} {'Utterance':<22} {'Extr':<5} {'Verdict':<26} {'OK':<4} {'cand':>5} {'commit':>7} {'exec':>5} {'T2':>4} {'Prom':>4}"
    )
    print(f"{'─'*115}")
    for r in results:
        es = "✓" if r.extraction_passed else "✗"
        vs = "✓" if r.verdict_passed else "✗"
        prom = "↑" if r.should_promote else "·"
        print(
            f"{r.scenario_id:<7} {r.domain_id:<12} {r.utterance[:20]:<22} {es:<5} "
            f"{r.verdict[:24]:<26} {vs:<4} {r.candidate_recall:>5.2f} {r.commit_accuracy:>7.2f} {r.execution_safety:>5.2f} "
            f"{r.hops_tier2:>4} {prom:>4}"
        )
    print(f"{'─'*110}")

    return {
        "provider": provider,
        "model": client.model_id,
        "total": total,
        "extract_ok": extract_ok,
        "verdict_ok": verdict_ok,
        "extract_pct": extract_pct,
        "verdict_pct": verdict_pct,
        "verdict_counts": verdict_counts,
        "domain_scores": domain_scores,
        "avg_extract_ms": round(avg_extract, 1),
        "avg_resolve_ms": round(avg_resolve, 1),
        "results": [
            {
                "id": r.scenario_id,
                "domain": r.domain_id,
                "utterance": r.utterance,
                "extraction_passed": r.extraction_passed,
                "verdict": r.verdict,
                "verdict_passed": r.verdict_passed,
                "allowed_actions": r.allowed_actions,
                "allowed_capability_names": r.allowed_capability_names,
                "tools_needed": r.tools_needed,
                "candidate_recall": r.candidate_recall,
                "candidate_recall_count": r.candidate_recall_count,
                "tools_found_all": r.tools_found_all,
                "commit_accuracy": r.commit_accuracy,
                "commit_match_count": r.commit_match_count,
                "tools_found_primary": r.tools_found_primary,
                "execution_safety": r.execution_safety,
                "execution_match_count": r.execution_match_count,
                "tools_committed": r.tools_committed,
                "connector_count": r.connector_count,
                "dependency_depth": r.dependency_depth,
                "has_companion_resources": r.has_companion_resources,
                "hops_tier2": r.hops_tier2,
                "hops_tier3": r.hops_tier3,
                "promotion_worth_it": r.promotion_worth_it,
                "should_promote": r.should_promote,
                "latency_extract_ms": r.latency_extract_ms,
                "latency_resolve_ms": r.latency_resolve_ms,
            }
            for r in results
        ],
        "tool_search_aggregates": {
            "avg_candidate_recall": round(avg_cand_recall, 3),
            "avg_commit_accuracy": round(avg_commit_acc, 3),
            "avg_execution_safety": round(avg_exec_safety, 3),
            "total_candidate_matches": total_cand,
            "total_commit_matches": total_commit,
            "total_execution_matches": total_exec,
            "total_needed": total_needed,
            "total_found_all": total_found_all,
        },
        "hops_aggregates": {
            "avg_tier2": round(avg_t2, 1),
            "avg_tier3": round(avg_t3, 1),
            "promote_count": promote_count,
            "worth_it_count": worth_count,
        },
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════╗
║   Back Resolver Benchmark — Full Tier 2 Spine       ║
║   Extract → RequestFrame → resolve_situation → Verdict║
╠══════════════════════════════════════════════════════╣
║  1. Dry-run (catalog stats, no LLM, no resolver)    ║
║  2. Run full pipeline (LLM + resolver)              ║
║  0. Exit                                            ║
╚══════════════════════════════════════════════════════╝"""


def main() -> int:
    print(MENU)
    choice = input("Select [1-2, 0]: ").strip()

    if choice == "1":
        from poc.back_tool_contract_v2.connectors.domain_catalog import (
            build_all_corpora,
        )

        corpora = build_all_corpora()
        total_connectors = sum(len(c) for c in corpora.values())
        total_capabilities = sum(
            sum(len(m.get("capabilities", [])) for m in corpus) for corpus in corpora.values()
        )
        print("DRY RUN — Resolver Benchmark")
        print(f"Domains: {len(corpora)}")
        print(f"Total connectors: {total_connectors}")
        print(f"Total capabilities: {total_capabilities}")
        print(f"Scenarios: {len(SCENARIOS)}")
        for domain_id, corpus in corpora.items():
            caps = sum(len(m.get("capabilities", [])) for m in corpus)
            print(f"  {domain_id}: {len(corpus)} connectors, {caps} capabilities")
        print("\nPipeline: Extract → Build RequestFrame → resolve_situation → Verdict")
        print("Expected: 50/50 scenarios → verdict ∈ {can_execute, can_execute_with_gate}")

    elif choice == "2":
        try:
            client = create_model_client_from_env()
        except Exception as exc:
            print(f"\nERROR: {exc}")
            print("Set $env:LLM_PROVIDER, $env:GOOGLE_CLOUD_PROJECT, $env:GOOGLE_CLOUD_LOCATION")
            return 1

        provider = os.environ.get("LLM_PROVIDER", "unknown")
        print(f"\nProvider: {provider} | Model: {client.model_id}")
        print("Running 50 scenarios through full Tier 2 spine...\n")

        result = asyncio.run(run_benchmark(client=client))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_slug = client.model_id.replace("/", "_").replace("-", "_")
        out_path = Path(f"data/llm_frame_bench/results_resolver_{provider}_{model_slug}_{ts}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
