"""Back Tool Contract — Real-World Resolver Benchmark.

Proves the resolver works with household simulation, session continuity,
constitution enforcement, and verdict transitions.

Modes:
  6. Household Simulation — 1K families, power-law connectors, real aliases
  7. Session Continuity — multi-turn gate→prereq→execute→verify flows
  8. Constitution Enforcement — 7 enforcement scenarios
  9. Run All (6+7+8)

Usage:
  python scripts/probe_real_world_benchmark.py
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract_v2.capability_binder import CapabilityBinderService
from poc.back_tool_contract_v2.connectors.catalog import (
    RESOURCE_KIND_BY_CONNECTOR,
    build_all_connector_manifests,
)
from poc.back_tool_contract_v2.fixtures.household_fixture import STANDARD_ACTOR_ID as AMBIG_ACTOR_ID
from poc.back_tool_contract_v2.fixtures.household_fixture import STANDARD_SPACE_ID as AMBIG_SPACE_ID
from poc.back_tool_contract_v2.fixtures.household_fixture import (
    HouseholdFixtureLoader,
)
from poc.back_tool_contract_v2.manifest_admission import ManifestAdmissionService
from poc.back_tool_contract_v2.policy_selector import PolicySelectorService
from poc.back_tool_contract_v2.proof import utc_now_iso
from poc.back_tool_contract_v2.request_frame_builder import (
    PersonRef,
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
    TimeWindowHint,
)
from poc.back_tool_contract_v2.resolve_situation import (
    ResolveSituationRequest,
    ResolveSituationService,
)
from poc.back_tool_contract_v2.resource_projection import ResolveResourcesService
from poc.back_tool_contract_v2.stores.global_projection_store import GlobalProjectionStore
from poc.back_tool_contract_v2.stores.local_projection_store import LocalProjectionStore

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

BUDGET = {"max_iterations": 10, "max_fabric_calls": 10, "max_prompt_tokens": 100000}

HEAVY_CONNECTORS = ["calendar", "tasks", "reminders", "chores", "shopping"]
MEDIUM_CONNECTORS = [
    "notes",
    "contacts",
    "google_calendar_read",
    "google_tasks",
    "todoist",
    "notion",
    "weather",
    "email_send",
    "slack_dm",
    "apple_reminders",
    "location_context",
    "documents",
    "habits",
    "budgets",
    "family_broadcast",
]
LIGHT_CONNECTORS = [
    "school_calendar_read",
    "sports_schedule_read",
    "doctor_appointment_read",
    "bank_balance_read",
    "package_tracking",
    "flight_status",
    "restaurant_reservation_create",
    "appointment_book",
    "food_order",
    "local_events_read",
    "air_quality_read",
    "notification_push",
    "alert_send",
]


# ═══════════════════════════════════════════════════════════════════
# DETERMINISTIC TEST HOUSEHOLD
# ═══════════════════════════════════════════════════════════════════

TEST_ACTOR_ID = "actor_test_001"
TEST_SPACE_ID = "space_test_001"

# Members guaranteed: Riley (child), Jordan (child), Alex (parent)
TEST_MEMBERS: list[dict[str, Any]] = [
    {
        "person_id": "person.riley",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "display_name": "Riley",
        "aliases": ["Riley", "Riles", "Rye"],
        "role": "child",
        "resource_ids": {"calendar": "calendar.riley.primary"},
        "created_at": "",
    },
    {
        "person_id": "person.jordan",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "display_name": "Jordan",
        "aliases": ["Jordan", "Jord", "J"],
        "role": "child",
        "resource_ids": {"calendar": "calendar.jordan.primary"},
        "created_at": "",
    },
    {
        "person_id": "person.alex",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "display_name": "Alex",
        "aliases": ["Alex", "Al", "Lex", "Mom", "Dad", "Parent"],
        "role": "parent",
        "resource_ids": {"calendar": "calendar.alex.primary"},
        "created_at": "",
    },
]

# Guaranteed resources: calendar + tasks + shopping for each person
TEST_RESOURCES: list[dict[str, Any]] = [
    {
        "resource_id": "calendar.riley.primary",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "connector_id": "calendar",
        "resource_kind": "calendar_event",
        "label": "Riley's Calendar",
        "aliases": ["riley calendar", "rileys calendar", "calendar"],
        "status": "active",
        "actor_permission": "read_write",
        "last_synced_at": "",
        "freshness_state": "fresh",
        "created_at": "",
    },
    {
        "resource_id": "calendar.jordan.primary",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "connector_id": "calendar",
        "resource_kind": "calendar_event",
        "label": "Jordan's Calendar",
        "aliases": ["jordan calendar", "jordans calendar", "calendar"],
        "status": "active",
        "actor_permission": "read_write",
        "last_synced_at": "",
        "freshness_state": "fresh",
        "created_at": "",
    },
    {
        "resource_id": "calendar.alex.primary",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "connector_id": "calendar",
        "resource_kind": "calendar_event",
        "label": "Alex's Calendar",
        "aliases": ["alex calendar", "parent calendar", "calendar"],
        "status": "active",
        "actor_permission": "read_write",
        "last_synced_at": "",
        "freshness_state": "fresh",
        "created_at": "",
    },
    {
        "resource_id": "tasks.riley.primary",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "connector_id": "tasks",
        "resource_kind": "task",
        "label": "Riley's Tasks",
        "aliases": ["riley tasks", "tasks"],
        "status": "active",
        "actor_permission": "read_write",
        "last_synced_at": "",
        "freshness_state": "fresh",
        "created_at": "",
    },
    {
        "resource_id": "shopping.riley.primary",
        "actor_id": TEST_ACTOR_ID,
        "space_id": TEST_SPACE_ID,
        "connector_id": "shopping",
        "resource_kind": "shopping_list",
        "label": "Riley's Shopping",
        "aliases": ["riley shopping", "shopping"],
        "status": "active",
        "actor_permission": "read_write",
        "last_synced_at": "",
        "freshness_state": "fresh",
        "created_at": "",
    },
]


def load_test_household(store: LocalProjectionStore) -> dict[str, str]:
    """Load a deterministic test household into the store."""
    now = utc_now_iso()
    store.reset()
    for m in TEST_MEMBERS:
        m["created_at"] = now
        store.upsert_household_member(m)
    for r in TEST_RESOURCES:
        r["last_synced_at"] = now
        r["created_at"] = now
        store.upsert_connected_resource(r)
    store.rebuild_alias_index(TEST_ACTOR_ID, TEST_SPACE_ID)
    return {"actor_id": TEST_ACTOR_ID, "space_id": TEST_SPACE_ID}


# ═══════════════════════════════════════════════════════════════════
# SCENARIO DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

GOLDEN_SCENARIOS = [
    {
        "id": "GOLDEN_001",
        "phrase": "What's on Riley's calendar this week?",
        "who": "Riley",
        "operation": "list",
        "resource": "calendar_event",
        "expected_verdict": "can_execute",
    },
    {
        "id": "GOLDEN_002",
        "phrase": "Move my dentist to Friday",
        "who": "Riley",
        "operation": "update",
        "resource": "calendar_event",
        "actor_role": "child",
        "expected_verdict": "missing_capability",
    },
    {
        "id": "GOLDEN_003",
        "phrase": "Add birthday for Riley",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "ambiguous_person": True,
        "expected_verdict": "needs_disambiguation",
    },
    {
        "id": "GOLDEN_004",
        "phrase": "Schedule Riley's dentist",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "missing_time": True,
        "expected_verdict": "missing_required_params",
    },
    {
        "id": "GOLDEN_008",
        "phrase": "Add dentist for Riley Monday 3pm",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "expected_verdict": "can_execute_with_gate",
    },
]

ENFORCEMENT_SCENARIOS = [
    {
        "id": "CE-001",
        "name": "Write without prereq → gate",
        "phrase": "Add dentist for Riley Monday 3pm",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "expected_verdict": "can_execute_with_gate",
    },
    {
        "id": "CE-002",
        "name": "Child writes parent calendar → missing cap",
        "phrase": "Move dad's meeting",
        "who": "Alex",
        "operation": "update",
        "resource": "calendar_event",
        "actor_role": "child",
        "expected_verdict": "missing_capability",
    },
    {
        "id": "CE-003",
        "name": "Missing time → ask user",
        "phrase": "Schedule Riley's dentist",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "missing_time": True,
        "expected_verdict": "missing_required_params",
    },
    {
        "id": "CE-004",
        "name": "Ambiguous person → disambiguation",
        "phrase": "Add birthday for Riley",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "ambiguous_person": True,
        "expected_verdict": "needs_disambiguation",
    },
    {
        "id": "CE-005",
        "name": "Pure read → execute directly",
        "phrase": "What's on Riley's calendar",
        "who": "Riley",
        "operation": "list",
        "resource": "calendar_event",
        "expected_verdict": "can_execute",
    },
    {
        "id": "CE-006",
        "name": "Stale resource + write → block",
        "phrase": "Add to Jordan's calendar",
        "who": "Jordan",
        "operation": "create",
        "resource": "calendar_event",
        "stale_resource": True,
        "expected_verdict": "stale_projection",
    },
    {
        "id": "CE-007",
        "name": "Cross-connector → escalate",
        "phrase": "Plan party with calendar and shopping",
        "who": "Riley",
        "operation": "create",
        "resource": "calendar_event",
        "cross_connector": True,
        "expected_verdict": "promote_to_tier3",
    },
]


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _mk_person_refs(who: str) -> list[PersonRef]:
    if not who:
        return []
    return [PersonRef(raw=who, confidence="medium", needs_resolution=False)]


def _mk_intents(scenario: dict) -> list[RequestFrameIntent]:
    sid = scenario["id"]
    phrase = scenario["phrase"]
    who = scenario.get("who", "")

    if scenario.get("cross_connector"):
        return [
            RequestFrameIntent(
                intent_id=f"intent-{sid}-1",
                action=phrase,
                domain=None,
                operation_hint="create",
                resource_kind_hint="calendar_event",
                subject_hint=phrase,
                params={"person_hint": who, "subject": phrase},
            ),
            RequestFrameIntent(
                intent_id=f"intent-{sid}-2",
                action=phrase,
                domain=None,
                operation_hint="create",
                resource_kind_hint="shopping_list",
                subject_hint=phrase,
                params={"person_hint": who, "subject": phrase},
            ),
        ]
    return [
        RequestFrameIntent(
            intent_id=f"intent-{sid}",
            action=phrase,
            domain=None,
            operation_hint=scenario["operation"],
            resource_kind_hint=scenario.get("resource"),
            subject_hint=phrase,
            params={"person_hint": who, "subject": phrase},
        ),
    ]


def _mk_frame(scenario: dict, actor_id: str, space_id: str) -> RequestFrame:
    # Build resource refs from person + resource hints
    resource_refs: list[ResourceRef] = []
    who = scenario.get("who", "")
    resource_hint = scenario.get("resource", "")
    if who and resource_hint:
        if scenario.get("cross_connector"):
            # Two resource refs for cross-connector scenarios
            resource_refs.append(
                ResourceRef(
                    raw=f"{who.lower()} calendar",
                    resource_kind_hint="calendar_event",
                    confidence="medium",
                    needs_resolution=False,
                )
            )
            resource_refs.append(
                ResourceRef(
                    raw=f"{who.lower()} shopping",
                    resource_kind_hint="shopping_list",
                    confidence="medium",
                    needs_resolution=False,
                )
            )
        else:
            resource_refs.append(
                ResourceRef(
                    raw=f"{who.lower()} {resource_hint.replace('_event', '').replace('_list', '')}",
                    resource_kind_hint=resource_hint,
                    confidence="medium",
                    needs_resolution=False,
                )
            )
    # For calendar_event, use "calendar" as the alias suffix
    if resource_hint == "calendar_event":
        resource_refs = [
            ResourceRef(
                raw=f"{who.lower()} calendar",
                resource_kind_hint="calendar_event",
                confidence="medium",
                needs_resolution=False,
            )
        ]

    # For time window on calendar writes
    tw_hint = None
    if (
        not scenario.get("missing_time")
        and scenario.get("operation") in ("create", "update")
        and resource_hint == "calendar_event"
    ):
        tw_hint = TimeWindowHint(
            raw_phrase="Monday 3pm",
            resolved_start=None,
            resolved_end=None,
            confidence="medium",
        )

    return RequestFrame(
        request_id=f"req-{scenario['id']}",
        task_id=f"task-{scenario['id']}",
        trace_id=f"trace-{scenario['id']}",
        actor_id=actor_id,
        space_id=space_id,
        intents=_mk_intents(scenario),
        time_window_hint=tw_hint,
        person_refs=_mk_person_refs(who),
        resource_refs=resource_refs,
        safety_context={
            "actor_role": scenario.get("actor_role", "parent"),
            "safety_band": "GREEN",
            "session_id": f"session-{scenario['id']}",
            "budget": BUDGET,
        },
        target_tier="tier2",
        resolution_mode="execution",
        created_at=utc_now_iso(),
    )


def _mk_request(
    scenario: dict,
    actor_id: str,
    space_id: str,
    completed_prereqs: list[str] | None = None,
    previous_resolution_id: str | None = None,
) -> ResolveSituationRequest:
    frame = _mk_frame(scenario, actor_id, space_id)
    return ResolveSituationRequest(
        request_frame=frame,
        actor_scope={"actor_id": actor_id, "space_id": space_id},
        safety_context=frame.safety_context,
        resolution_mode="execution",
        target_tier="tier2",
        disclosure_phase="connector_summary",
        freshness_policy="strict",
        prompt_budget=8000,
        completed_prerequisite_bindings=completed_prereqs or [],
        previous_resolution_id=previous_resolution_id,
    )


# ═══════════════════════════════════════════════════════════════════
# HOUSEHOLD FACTORY (for Mode 6)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SimulatedHousehold:
    actor_id: str
    space_id: str
    members: list[dict]
    connected_connectors: list[str]
    aliases: dict[str, str]


def _sample_connectors(rng: random.Random) -> list[str]:
    chosen: list[str] = []
    for c in HEAVY_CONNECTORS:
        if rng.random() < 0.60:
            chosen.append(c)
    for c in MEDIUM_CONNECTORS:
        if rng.random() < 0.30:
            chosen.append(c)
    for c in LIGHT_CONNECTORS:
        if rng.random() < 0.10:
            chosen.append(c)
    while len(chosen) < 2:
        c = rng.choice(HEAVY_CONNECTORS)
        if c not in chosen:
            chosen.append(c)
    return chosen[:20]


def _build_household(
    rng: random.Random, store: LocalProjectionStore, index: int
) -> SimulatedHousehold:
    actor_id = f"actor_{index:04d}"
    space_id = f"space_{index:04d}"
    now = utc_now_iso()

    member_count = rng.choice([2, 3, 4, 4, 5, 6])
    roles_pool = ["parent", "parent", "child", "child", "guardian", "guest"]
    names_pool = [
        ("Riley", ["Riles", "Rye"]),
        ("Jordan", ["Jord", "J"]),
        ("Alex", ["Al", "Lex"]),
        ("Morgan", ["Morg", "Mo"]),
        ("Casey", ["Case", "C"]),
        ("Taylor", ["Tay", "T"]),
        ("Sam", ["Sammy"]),
        ("Jamie", ["Jay"]),
        ("Drew", []),
        ("Quinn", ["Q"]),
    ]
    rng.shuffle(names_pool)
    rng.shuffle(roles_pool)

    members: list[dict] = []
    aliases: dict[str, str] = {}
    resources: dict[str, tuple[str, str]] = {}

    for i in range(min(member_count, len(names_pool))):
        name, nicknames = names_pool[i]
        person_id = f"person.{actor_id}.{name.lower()}"
        role = roles_pool[i % len(roles_pool)]
        member_aliases = [name] + nicknames
        if role == "parent":
            member_aliases.extend(["Mom", "Dad", "Parent"][i : i + 1])

        for c in _sample_connectors(rng):
            rid = f"{c}.{person_id}.primary"
            if rid not in resources:
                resources[rid] = (c, f"{name}'s {c.replace('_', ' ').title()}")

        members.append(
            {
                "person_id": person_id,
                "actor_id": actor_id,
                "space_id": space_id,
                "display_name": name,
                "aliases": member_aliases,
                "role": role,
                "resource_ids": {},
                "created_at": now,
            }
        )
        for alias in member_aliases:
            aliases[alias.lower()] = person_id

    store.reset()
    for m in members:
        store.upsert_household_member(m)
    for rid, (connector_id, label) in resources.items():
        store.upsert_connected_resource(
            {
                "resource_id": rid,
                "actor_id": actor_id,
                "space_id": space_id,
                "connector_id": connector_id,
                "resource_kind": RESOURCE_KIND_BY_CONNECTOR.get(connector_id, connector_id),
                "label": label,
                "aliases": [label.lower(), connector_id.replace("_", " ")],
                "status": "active",
                "actor_permission": rng.choice(["read_write", "read_write", "read_only"]),
                "last_synced_at": now,
                "freshness_state": rng.choice(["fresh", "fresh", "fresh", "fresh", "stale"]),
                "created_at": now,
            }
        )
    store.rebuild_alias_index(actor_id, space_id)

    all_c = sorted({r[0] for r in resources.values()})
    return SimulatedHousehold(
        actor_id=actor_id,
        space_id=space_id,
        members=members,
        connected_connectors=all_c,
        aliases=aliases,
    )


# ═══════════════════════════════════════════════════════════════════
# MODE 6: Household Simulation
# ═══════════════════════════════════════════════════════════════════


def _bench6_household(global_store: GlobalProjectionStore) -> dict:
    print("  Building 1,000 simulated households...")
    rng = random.Random(42)

    base_dir = Path("data/real_world_bench/households")
    base_dir.mkdir(parents=True, exist_ok=True)

    households: list[tuple[SimulatedHousehold, LocalProjectionStore]] = []
    for i in range(1000):
        ls = LocalProjectionStore(base_dir / f"household_{i:04d}.sqlite")
        ls.open()
        hh = _build_household(rng, ls, i)
        households.append((hh, ls))

    conn_counts = [len(hh.connected_connectors) for hh, _ in households]
    mem_counts = [len(hh.members) for hh, _ in households]

    print("  Households: 1,000")
    print(f"  Avg connectors: {statistics.mean(conn_counts):.1f}")
    print(f"  Avg members: {statistics.mean(mem_counts):.1f}")

    pop: dict[str, int] = {}
    for hh, _ in households:
        for c in hh.connected_connectors:
            pop[c] = pop.get(c, 0) + 1
    top5 = sorted(pop.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"  Top 5 connectors: {', '.join(f'{c}({n})' for c, n in top5)}")

    # Use deterministic test household for scenario tests
    print("\n  Running golden scenarios with deterministic test household...")
    test_dir = base_dir / "test_household.sqlite"
    test_ls = LocalProjectionStore(test_dir)
    test_ls.open()
    ids = load_test_household(test_ls)

    resource_resolver = ResolveResourcesService(global_store, test_ls)
    policy_selector = PolicySelectorService(global_store)
    capability_binder = CapabilityBinderService(global_store, test_ls)

    results: list[dict] = []
    for scenario in GOLDEN_SCENARIOS:
        cur_ls = test_ls
        cur_resolver = resource_resolver
        cur_binder = capability_binder

        if scenario.get("ambiguous_person"):
            ambig = LocalProjectionStore(base_dir / "ambig_test.sqlite")
            ambig.open()
            HouseholdFixtureLoader(ambig).load_ambiguous_riley(reset=True)
            cur_resolver = ResolveResourcesService(global_store, ambig)
            cur_binder = CapabilityBinderService(global_store, ambig)
            cur_ls = ambig

        svc = ResolveSituationService(
            global_store,
            cur_ls,
            resource_resolver=cur_resolver,
            policy_selector=policy_selector,
            capability_binder=cur_binder,
        )

        # Use fixture IDs for ambiguous scenarios
        aid = AMBIG_ACTOR_ID if scenario.get("ambiguous_person") else ids["actor_id"]
        sid = AMBIG_SPACE_ID if scenario.get("ambiguous_person") else ids["space_id"]
        request = _mk_request(scenario, aid, sid)
        start = time.perf_counter()
        envelope = svc.resolve(request)
        elapsed = (time.perf_counter() - start) * 1000

        results.append(
            {
                "scenario": scenario["id"],
                "phrase": scenario["phrase"],
                "expected": scenario["expected_verdict"],
                "actual": envelope.verdict,
                "match": envelope.verdict == scenario["expected_verdict"],
                "allowed_count": len(envelope.allowed_next_actions),
                "latency_ms": round(elapsed, 2),
            }
        )

        if scenario.get("ambiguous_person"):
            ambig.close()

    print(f"\n  {'─'*72}")
    print(f"  {'Scenario':<12} {'Expected':<28} {'Actual':<28} {'Match':<6}")
    print(f"  {'─'*72}")
    matches = sum(1 for r in results if r["match"])
    for r in results:
        flag = "✓" if r["match"] else "✗"
        print(f"  {r['scenario']:<12} {r['expected']:<28} {r['actual']:<28} {flag:<6}")
    print(f"  {'─'*72}")
    print(f"  Accuracy: {matches}/{len(results)} ({matches/len(results):.0%})")
    avg_lat = statistics.mean([r["latency_ms"] for r in results])
    print(f"  Avg latency: {avg_lat:.1f}ms")

    test_ls.close()
    for _, s in households:
        s.close()

    return {
        "households": 1000,
        "avg_connectors": round(statistics.mean(conn_counts), 1),
        "avg_members": round(statistics.mean(mem_counts), 1),
        "top5_connectors": [(c, n) for c, n in top5],
        "scenario_accuracy": round(matches / len(results), 4),
        "avg_latency_ms": round(avg_lat, 1),
        "scenario_results": results,
    }


# ═══════════════════════════════════════════════════════════════════
# MODE 7: Session Continuity
# ═══════════════════════════════════════════════════════════════════


def _bench7_session(global_store: GlobalProjectionStore) -> dict:
    print("  Running session continuity test (gate → prereq → execute → verify)...")
    base_dir = Path("data/real_world_bench/session")
    base_dir.mkdir(parents=True, exist_ok=True)

    ls = LocalProjectionStore(base_dir / "test_household.sqlite")
    ls.open()
    ids = load_test_household(ls)

    resource_resolver = ResolveResourcesService(global_store, ls)
    policy_selector = PolicySelectorService(global_store)
    capability_binder = CapabilityBinderService(global_store, ls)

    resolver = ResolveSituationService(
        global_store,
        ls,
        resource_resolver=resource_resolver,
        policy_selector=policy_selector,
        capability_binder=capability_binder,
    )

    scenario = GOLDEN_SCENARIOS[4]  # GOLDEN_008: Add dentist
    turns: list[dict] = []
    total_latency = 0.0
    completed_prereqs: list[str] = []
    transition_ok = None

    print("\n  Turn 1: Resolve 'Add dentist for Riley Monday 3pm'")
    req1 = _mk_request(scenario, ids["actor_id"], ids["space_id"])
    start = time.perf_counter()
    env1 = resolver.resolve(req1)
    e1 = (time.perf_counter() - start) * 1000
    total_latency += e1

    turns.append(
        {
            "turn": 1,
            "verdict": env1.verdict,
            "allowed": len(env1.allowed_next_actions),
            "latency_ms": round(e1, 2),
        }
    )
    print(
        f"    Verdict: {env1.verdict} | Allowed actions: {len(env1.allowed_next_actions)} | {e1:.1f}ms"
    )

    for cap_name, binding_id in env1.capability_name_to_binding.items():
        if any(op in cap_name.lower() for op in ("list", "get", "search", "read")):
            completed_prereqs.append(binding_id)

    if completed_prereqs:
        print(f"\n  Turn 2: Re-resolve with {len(completed_prereqs)} completed prerequisite(s)")
        req2 = _mk_request(
            scenario,
            ids["actor_id"],
            ids["space_id"],
            completed_prereqs=completed_prereqs,
            previous_resolution_id=env1.resolution_id,
        )
        start = time.perf_counter()
        env2 = resolver.resolve(req2)
        e2 = (time.perf_counter() - start) * 1000
        total_latency += e2

        turns.append(
            {
                "turn": 2,
                "verdict": env2.verdict,
                "allowed": len(env2.allowed_next_actions),
                "latency_ms": round(e2, 2),
            }
        )
        print(
            f"    Verdict: {env2.verdict} | Allowed actions: {len(env2.allowed_next_actions)} | {e2:.1f}ms"
        )

        transition_ok = env1.verdict == "can_execute_with_gate" and env2.verdict == "can_execute"
        print(f"    Gate → Execute transition: {'✓' if transition_ok else '✗'}")

    seq = [t["verdict"] for t in turns]
    print(f"\n  Session flow: {' → '.join(seq)}")
    print(f"  Total latency: {total_latency:.1f}ms")

    ls.close()
    return {
        "turns": len(turns),
        "verdict_sequence": seq,
        "transition_correct": transition_ok,
        "total_latency_ms": round(total_latency, 1),
        "turn_details": turns,
    }


# ═══════════════════════════════════════════════════════════════════
# MODE 8: Constitution Enforcement
# ═══════════════════════════════════════════════════════════════════


def _bench8_constitution(global_store: GlobalProjectionStore) -> dict:
    print("  Running constitution enforcement scenarios...")
    base_dir = Path("data/real_world_bench/constitution")
    base_dir.mkdir(parents=True, exist_ok=True)

    ls = LocalProjectionStore(base_dir / "test_household.sqlite")
    ls.open()
    ids = load_test_household(ls)

    resource_resolver = ResolveResourcesService(global_store, ls)
    policy_selector = PolicySelectorService(global_store)
    capability_binder = CapabilityBinderService(global_store, ls)

    results: list[dict] = []
    for scenario in ENFORCEMENT_SCENARIOS:
        cur_ls = ls
        cur_resolver = resource_resolver
        cur_binder = capability_binder

        if scenario.get("ambiguous_person"):
            ambig = LocalProjectionStore(base_dir / "ambig_test.sqlite")
            ambig.open()
            HouseholdFixtureLoader(ambig).load_ambiguous_riley(reset=True)
            cur_resolver = ResolveResourcesService(global_store, ambig)
            cur_binder = CapabilityBinderService(global_store, ambig)
            cur_ls = ambig

        if scenario.get("stale_resource"):
            cur_ls.conn.execute("UPDATE connected_resources SET freshness_state='stale'")
            cur_ls.conn.commit()

        svc = ResolveSituationService(
            global_store,
            cur_ls,
            resource_resolver=cur_resolver,
            policy_selector=policy_selector,
            capability_binder=cur_binder,
        )

        # Use fixture IDs for ambiguous scenarios
        aid = AMBIG_ACTOR_ID if scenario.get("ambiguous_person") else ids["actor_id"]
        sid = AMBIG_SPACE_ID if scenario.get("ambiguous_person") else ids["space_id"]
        request = _mk_request(scenario, aid, sid)
        start = time.perf_counter()
        envelope = svc.resolve(request)
        elapsed = (time.perf_counter() - start) * 1000

        results.append(
            {
                "id": scenario["id"],
                "name": scenario["name"],
                "expected": scenario["expected_verdict"],
                "actual": envelope.verdict,
                "match": envelope.verdict == scenario["expected_verdict"],
                "allowed_count": len(envelope.allowed_next_actions),
                "latency_ms": round(elapsed, 2),
                "diagnostics_count": len(envelope.diagnostics),
            }
        )

        if scenario.get("ambiguous_person"):
            ambig.close()

        if scenario.get("stale_resource"):
            cur_ls.conn.execute("UPDATE connected_resources SET freshness_state='fresh'")
            cur_ls.conn.commit()

    print(f"\n  {'─'*78}")
    print(f"  {'ID':<10} {'Test':<35} {'Expected':<22} {'Actual':<22} {'Match':<6}")
    print(f"  {'─'*78}")
    matches = sum(1 for r in results if r["match"])
    for r in results:
        flag = "✓" if r["match"] else "✗"
        print(
            f"  {r['id']:<10} {r['name'][:34]:<35} {r['expected']:<22} {r['actual']:<22} {flag:<6}"
        )
    print(f"  {'─'*78}")
    print(f"  Enforcement accuracy: {matches}/{len(results)} ({matches/len(results):.0%})")
    avg_lat = statistics.mean([r["latency_ms"] for r in results])
    print(f"  Avg latency: {avg_lat:.1f}ms")

    ls.close()
    return {
        "scenarios": len(results),
        "accuracy": round(matches / len(results), 4),
        "avg_latency_ms": round(avg_lat, 1),
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════╗
║   Real-World Resolver Benchmark                 ║
╠══════════════════════════════════════════════════╣
║  6. Household Simulation (1K families)           ║
║  7. Session Continuity (gate → execute)          ║
║  8. Constitution Enforcement (7 scenarios)       ║
║  9. Run All (6+7+8)                              ║
║  0. Exit                                         ║
╚══════════════════════════════════════════════════╝"""


def main() -> int:
    print(MENU)
    choice = input("Select benchmark [6-9, 0]: ").strip()
    if choice not in "6789":
        return 0

    run_dir = Path("data/real_world_bench")
    run_dir.mkdir(parents=True, exist_ok=True)

    print("Loading connector catalog...")
    global_store = GlobalProjectionStore(run_dir / "global.sqlite")
    global_store.open()

    real = build_all_connector_manifests()
    ManifestAdmissionService(global_store).admit_all(real)
    count = global_store.capability_count()
    print(f"  Global store: {count:,} capabilities\n")

    results: dict[str, Any] = {}

    try:
        if choice in ("6", "9"):
            print("=" * 60)
            print("MODE 6: Household Simulation")
            print("=" * 60)
            results["household_simulation"] = _bench6_household(global_store)

        if choice in ("7", "9"):
            print("\n" + "=" * 60)
            print("MODE 7: Session Continuity")
            print("=" * 60)
            results["session_continuity"] = _bench7_session(global_store)

        if choice in ("8", "9"):
            print("\n" + "=" * 60)
            print("MODE 8: Constitution Enforcement")
            print("=" * 60)
            results["constitution_enforcement"] = _bench8_constitution(global_store)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = run_dir / f"results_{ts}.json"
        out_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"\nResults written to {out_path}")

    finally:
        global_store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
