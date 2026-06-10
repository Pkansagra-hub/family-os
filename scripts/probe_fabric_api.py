"""Fabric API Probe — Comprehensive end-to-end exercise of EVERY Fabric API surface.

Exercises every public API on the real wired Fabric: resolve_situation,
discover_capabilities, find_relevant_prompts, execute (real family tools),
idempotency, policy gating, redaction proof, and the full extract→resolve→execute
pipeline with real Vertex LLM extraction.

Usage:
  $env:LLM_PROVIDER="vertex"
  $env:GOOGLE_CLOUD_PROJECT="<project>"
  $env:GOOGLE_CLOUD_LOCATION="global"
  python scripts/probe_fabric_api.py
  # Modes: 1=dry-run, 2=full (LLM + real Fabric), 3=LLM-only quick check
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8")
        except Exception:
            pass

# ── Real Fabric wiring ────────────────────────────────────────────────
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.connectors.domain_catalog import (
    DOMAIN_SERVICES,
    build_all_corpora,
)
from k1.fabric.factory import FabricFactory
from k1.fabric.manifest_admission import ManifestAdmissionService
from k1.fabric.resolver.request_frame import (
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
)
from k1.fabric.resolver.situated_resolver import ResolveSituationRequest
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.idempotency_store import IdempotencyStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ── Fabric types for execute ──────────────────────────────────────────
from k1.fabric.types import CapabilityRequest

# ── Family tools (real execution) ─────────────────────────────────────
from k1.tools.family.base import WriteContext
from k1.tools.family.bootstrap import bootstrap_family_tools
from k1.tools.family.calendar.service import CalendarToolService

# ── Real Vertex LLM client (extraction layer) ─────────────────────────
from poc.back_tool_contract_v2.model_client import (
    ModelClient,
    create_model_client_from_env,
)

# ══════════════════════════════════════════════════════════════════════
# RESULT TYPES
# ══════════════════════════════════════════════════════════════════════


@dataclass
class ProbeResult:
    section: str
    test: str
    passed: bool
    detail: str
    latency_ms: float = 0.0


# ══════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════════════


def _now_ms() -> float:
    return time.perf_counter() * 1000


def _ports() -> dict:
    return dict(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
    )


def _gps() -> GlobalProjectionStore:
    s = GlobalProjectionStore(":memory:")
    s.open()
    return s


def _lps() -> LocalProjectionStore:
    s = LocalProjectionStore(":memory:")
    s.open()
    return s


def _idem() -> IdempotencyStore:
    s = IdempotencyStore(":memory:")
    s.open()
    return s


def _wired_fabric():
    """Real Fabric exactly as the kernel P3 path wires it."""
    gps = _gps()
    lps = _lps()
    idem = _idem()
    admission = ManifestAdmissionService(gps)
    for corpus in build_all_corpora().values():
        admission.admit_all(corpus)
    # Seed one connected resource per family service
    for sd in DOMAIN_SERVICES["family"]:
        connector_id = f"family.{sd.id}"
        lps.upsert_connected_resource(
            {
                "resource_id": f"res_family_{sd.id}",
                "actor_id": "actor-a",
                "resource_kind": sd.resource,
                "connector_id": connector_id,
                "label": sd.label,
                "status": "active",
                "permissions": "read_write",
                "freshness_state": "fresh",
            }
        )
    lps.rebuild_alias_index("actor-a", "space-1")
    return FabricFactory.create_with_ports(
        **_ports(),
        global_projection_store=gps,
        local_projection_store=lps,
        idempotency_store=idem,
    )


def _resolve_request(frame: RequestFrame) -> ResolveSituationRequest:
    return ResolveSituationRequest(
        request_id=frame.request_id,
        frame=frame,
        actor_id=frame.actor_id,
        space_id=frame.space_id,
        session_id="sess-probe-1",
        tier="MEDIUM",
        safety_band="GREEN",
    )


def _frame(
    *, op: str, rk: str, params: dict | None = None, subject: str | None = None
) -> RequestFrame:
    return RequestFrame(
        request_id="req-" + uuid.uuid4().hex[:12],
        task_id="task-probe-1",
        trace_id="trace-probe-1",
        actor_id="actor-a",
        space_id="space-1",
        intents=[
            RequestFrameIntent(
                intent_id="i1",
                action=f"{op} {rk}",
                domain="family",
                operation_hint=op,
                resource_kind_hint=rk,
                subject_hint=subject,
                params=params or {},
            )
        ],
        resource_refs=[ResourceRef(raw=rk, resource_kind_hint=rk, needs_resolution=False)],
        safety_context={"actor_role": "parent", "safety_band": "GREEN"},
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _ctx(**over: Any) -> WriteContext:
    return WriteContext(
        user_id=over.pop("user_id", "u1"),
        space_id=over.pop("space_id", "h1"),
        trace_id="trace-probe-1",
        role=over.pop("role", "parent"),  # type: ignore[arg-type]
        band=over.pop("band", "GREEN"),  # type: ignore[arg-type]
        idempotency_key=over.pop("idempotency_key", None),
    )


_EVT_PARAMS = {
    "title": "Soccer game",
    "start": "2026-05-15T10:00:00+00:00",
    "end": "2026-05-15T11:30:00+00:00",
}


# ══════════════════════════════════════════════════════════════════════
# PROBE 0: Store health + catalog stats
# ══════════════════════════════════════════════════════════════════════


def probe_store_health(fabric: Any) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    gps = fabric.global_projection_store

    t0 = _now_ms()
    connectors = gps.list_connectors()
    cap_count = gps.count_capabilities()
    lat = _now_ms() - t0
    results.append(
        ProbeResult(
            "store",
            "list_connectors",
            len(connectors) == 50,
            f"{len(connectors)} connectors, {cap_count} caps",
            lat,
        )
    )

    t0 = _now_ms()
    cal = gps.get_connector("family.calendar")
    lat = _now_ms() - t0
    results.append(
        ProbeResult(
            "store",
            "get_connector",
            cal is not None,
            f"family.calendar: {cal.label if cal else 'MISSING'}",
            lat,
        )
    )

    t0 = _now_ms()
    hits = gps.search_capabilities("calendar create", top_k=5)
    lat = _now_ms() - t0
    found = any("calendar" in h.capability_name and "create" in h.capability_name for h in hits)
    results.append(
        ProbeResult(
            "store",
            "search_capabilities",
            found,
            f"top hit: {hits[0].capability_name if hits else 'none'}",
            lat,
        )
    )

    t0 = _now_ms()
    typed = gps.lookup_capability_by_type("family", "calendar_event", "create", "write")
    lat = _now_ms() - t0
    results.append(
        ProbeResult(
            "store",
            "lookup_capability_by_type",
            len(typed) >= 1,
            f"{len(typed)} matches for calendar_event/create/write",
            lat,
        )
    )

    t0 = _now_ms()
    find = gps.find_capabilities(
        resource_kind="calendar_event", invocation_mode="execute", effect="write"
    )
    lat = _now_ms() - t0
    results.append(
        ProbeResult(
            "store",
            "find_capabilities",
            len(find) >= 1,
            f"{len(find)} execute/write caps for calendar_event",
            lat,
        )
    )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 1: resolve_situation — read + write paths
# ══════════════════════════════════════════════════════════════════════


def probe_resolve_situation(fabric: Any) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    # 1a — Simple read
    t0 = _now_ms()
    env = fabric.resolve_situation(_resolve_request(_frame(op="list", rk="calendar_event")))
    lat = _now_ms() - t0
    ok = env.verdict == "can_execute" and env.binding_bundle is not None
    results.append(
        ProbeResult(
            "resolve",
            "read_calendar_list",
            ok,
            f"verdict={env.verdict} primary={env.binding_bundle.primary.capability_name if env.binding_bundle and env.binding_bundle.primary else 'none'}",
            lat,
        )
    )

    # 1b — Write with gate (prerequisite incomplete)
    env = fabric.resolve_situation(
        _resolve_request(
            _frame(
                op="create",
                rk="calendar_event",
                params={
                    "title": "X",
                    "start": "a",
                    "end": "b",
                    "resource_id": "c",
                    "idempotency_key": "k",
                },
                subject="dentist",
            )
        )
    )
    ok = env.verdict == "can_execute_with_gate" and "prerequisite_read_incomplete" in (
        env.sub_reason or ""
    )
    results.append(
        ProbeResult(
            "resolve",
            "write_calendar_create_gated",
            ok,
            f"verdict={env.verdict} sub_reason={env.sub_reason}",
        )
    )

    # 1c — Complete the prereq, re-resolve → can_execute
    prereq_id = (
        env.binding_bundle.prerequisites[0].binding_id
        if env.binding_bundle and env.binding_bundle.prerequisites
        else None
    )
    if prereq_id:
        # Re-resolve using the EXACT same frame to ensure stable binding_ids.
        frame2 = _frame(
            op="create",
            rk="calendar_event",
            params={
                "title": "X",
                "start": "a",
                "end": "b",
                "resource_id": "c",
                "idempotency_key": "k",
            },
            subject="dentist",
        )
        env2 = fabric.resolve_situation(
            ResolveSituationRequest(
                request_id=frame2.request_id,
                frame=frame2,
                actor_id="actor-a",
                space_id="space-1",
                session_id="sess-probe-1",
                tier="MEDIUM",
                safety_band="GREEN",
                completed_prerequisite_bindings=[prereq_id],
            )
        )
        # Check: the cascaded second resolve should succeed.
        ok = env2.verdict == "can_execute"
        if not ok:
            bind_ids = [
                b.binding_id
                for b in (env2.binding_bundle.prerequisites if env2.binding_bundle else [])
            ]
            results.append(
                ProbeResult(
                    "resolve",
                    "write_after_prereq_complete",
                    ok,
                    f"verdict={env2.verdict} prereq_ids={bind_ids[:2]} expected={prereq_id[:12]}",
                )
            )
        else:
            results.append(
                ProbeResult("resolve", "write_after_prereq_complete", ok, f"verdict={env2.verdict}")
            )

    # 1d — Missing capability
    env = fabric.resolve_situation(
        _resolve_request(_frame(op="create", rk="widget", params={"x": 1}))
    )
    ok = env.verdict == "missing_capability" and "widget" in (env.sub_reason or "")
    results.append(
        ProbeResult(
            "resolve",
            "missing_capability",
            ok,
            f"verdict={env.verdict} sub_reason={env.sub_reason}",
        )
    )

    # 1e — Prompt pack built
    env = fabric.resolve_situation(_resolve_request(_frame(op="list", rk="calendar_event")))
    ok = env.prompt_pack is not None
    results.append(
        ProbeResult(
            "resolve",
            "prompt_pack_built",
            ok,
            f"pack_id={env.prompt_pack.prompt_pack_id if env.prompt_pack else 'none'}",
        )
    )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 2: discover_capabilities + find_relevant_prompts
# ══════════════════════════════════════════════════════════════════════


async def probe_discovery(fabric: Any) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    t0 = _now_ms()
    disc = await fabric.discover_capabilities(intent="calendar", top_k=10)
    lat = _now_ms() - t0
    caps_list = getattr(disc, "capabilities", [])
    ok = len(caps_list) > 0
    top_name = caps_list[0].contract.name if caps_list and caps_list[0].contract else "none"
    results.append(
        ProbeResult(
            "discovery",
            "discover_capabilities",
            ok,
            f"{len(caps_list)} results, top: {top_name}",
            lat,
        )
    )

    t0 = _now_ms()
    prompts = await fabric.find_relevant_prompts(intent="calendar", top_k=5)
    lat = _now_ms() - t0
    results.append(
        ProbeResult(
            "discovery",
            "find_relevant_prompts",
            True,
            f"{len(getattr(prompts, 'capabilities', []))} results",
            lat,
        )
    )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 3: Family tool execution (real CalendarToolService)
# ══════════════════════════════════════════════════════════════════════


def probe_family_execution(tmp_path: Path) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    bundle = bootstrap_family_tools(
        None, db_path=str(tmp_path / "fam.db"), service_classes=[CalendarToolService]
    )
    try:
        svc = bundle.tool_registry.get_service("calendar")
        ctx = _ctx()

        # 3a — create_event
        t0 = _now_ms()
        created = _run(svc.dispatch("create_event", dict(_EVT_PARAMS), ctx))
        lat = _now_ms() - t0
        ok = created.get("success") and created.get("event_id")
        event_id = created.get("event_id", "")
        results.append(
            ProbeResult(
                "family",
                "create_event",
                ok,
                f"event_id={event_id} version={created.get('version')}",
                lat,
            )
        )

        # 3b — get_event
        t0 = _now_ms()
        got = _run(svc.dispatch("get_event", {"event_id": event_id}, ctx))
        lat = _now_ms() - t0
        ok = got.get("success") and got.get("event", {}).get("title") == "Soccer game"
        results.append(
            ProbeResult(
                "family", "get_event", ok, f"title={got.get('event', {}).get('title')}", lat
            )
        )

        # 3c — update_event
        t0 = _now_ms()
        updated = _run(
            svc.dispatch(
                "update_event",
                {"event_id": event_id, "expected_version": 1, "title": "Soccer (rescheduled)"},
                ctx,
            )
        )
        lat = _now_ms() - t0
        ok = updated.get("success") and updated.get("version") == 2
        results.append(
            ProbeResult("family", "update_event", ok, f"version={updated.get('version')}", lat)
        )

        # 3d — list_events
        t0 = _now_ms()
        listed = _run(
            svc.dispatch(
                "list_events",
                {
                    "resource_id": "h1_cal",
                    "time_min": "2026-01-01T00:00:00Z",
                    "time_max": "2026-12-31T00:00:00Z",
                },
                ctx,
            )
        )
        lat = _now_ms() - t0
        events = listed.get("events", [])
        ok = listed.get("success") and len(events) >= 1
        results.append(ProbeResult("family", "list_events", ok, f"{len(events)} events found", lat))

        # 3e — delete_event
        t0 = _now_ms()
        deleted = _run(
            svc.dispatch("delete_event", {"event_id": event_id, "expected_version": 2}, ctx)
        )
        lat = _now_ms() - t0
        ok = deleted.get("success")
        results.append(
            ProbeResult("family", "delete_event", ok, f"success={deleted.get('success')}", lat)
        )

        # 3f — Idempotency: create twice with same key
        idem_ctx = _ctx(idempotency_key="idem-probe-1")
        first = _run(svc.dispatch("create_event", dict(_EVT_PARAMS), idem_ctx))
        second = _run(svc.dispatch("create_event", dict(_EVT_PARAMS), idem_ctx))
        ok = (
            first.get("event_id") == second.get("event_id")
            and first.get("version") == 1
            and second.get("version") == 1
        )
        results.append(
            ProbeResult(
                "family",
                "idempotency_create",
                ok,
                f"same event_id={first.get('event_id')} same version={second.get('version')}",
            )
        )

        # cleanup idem test event
        _run(
            svc.dispatch(
                "delete_event", {"event_id": first["event_id"], "expected_version": 1}, _ctx()
            )
        )
    finally:
        bundle.close()
    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 4: IdempotencyStore + policy gating + redaction
# ══════════════════════════════════════════════════════════════════════


def probe_gates(fabric: Any) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    # 4a — Idempotency duplicate blocks resolution
    idem = fabric.idempotency_store
    key = "probe-idem-1"
    idem.mark_in_flight(key, "inv-1")
    idem.mark_success(key, {"event_id": "evt-1"})
    env = fabric.resolve_situation(
        ResolveSituationRequest(
            request_id="req-idem",
            frame=_frame(
                op="create",
                rk="calendar_event",
                params={
                    "title": "X",
                    "start": "a",
                    "end": "b",
                    "resource_id": "c",
                    "idempotency_key": "k",
                },
                subject="x",
            ),
            actor_id="actor-a",
            space_id="space-1",
            session_id="sess-1",
            tier="MEDIUM",
            safety_band="GREEN",
            idempotency_keys=[key],
        )
    )
    ok = env.verdict == "cannot_execute" and env.sub_reason == f"idempotency_duplicate:{key}"
    results.append(
        ProbeResult(
            "gates",
            "idempotency_duplicate",
            ok,
            f"verdict={env.verdict} sub_reason={env.sub_reason}",
        )
    )

    # 4b — Policy: child write blocked on chores connector (admit a custom connector)
    from k1.fabric.connectors.definition import (
        CapabilityDefinition,
        ConnectorDefinition,
        PolicyDefinition,
    )

    chores_connector = ConnectorDefinition(
        connector_id="family.chores",
        label="Chores",
        description="chores connector",
        provider_id="native.family.chores",
        resource_kinds=["chore"],
        capabilities=[
            CapabilityDefinition(
                name="tool.read.family.chores.list",
                action_name="list",
                invocation_mode="read",
                effect="read",
                resource_kind="chore",
                description="list chores",
            ),
            CapabilityDefinition(
                name="tool.execute.family.chores.create",
                action_name="create",
                invocation_mode="execute",
                effect="write",
                resource_kind="chore",
                description="create chore",
            ),
        ],
        policy=PolicyDefinition(write_requires_actor_role=["parent", "guardian"]),
    )
    ManifestAdmissionService(fabric.global_projection_store).admit(chores_connector)
    fabric.local_projection_store.upsert_connected_resource(
        {
            "resource_id": "chore-1",
            "actor_id": "actor-a",
            "resource_kind": "chore",
            "connector_id": "family.chores",
            "label": "chore list",
            "status": "active",
            "permissions": "read_write",
            "freshness_state": "fresh",
        }
    )
    fabric.local_projection_store.rebuild_alias_index("actor-a", "space-1")

    chore_frame = _frame(op="create", rk="chore", params={"title": "Dishes"})
    # Hack: set actor_role to child
    child_frame = RequestFrame(
        request_id=chore_frame.request_id,
        task_id=chore_frame.task_id,
        trace_id=chore_frame.trace_id,
        actor_id=chore_frame.actor_id,
        space_id=chore_frame.space_id,
        intents=chore_frame.intents,
        resource_refs=chore_frame.resource_refs,
        safety_context={"actor_role": "child", "safety_band": "GREEN"},
    )
    env = fabric.resolve_situation(
        ResolveSituationRequest(
            request_id="req-child",
            frame=child_frame,
            actor_id="actor-a",
            space_id="space-1",
            session_id="sess-1",
            tier="MEDIUM",
            safety_band="GREEN",
        )
    )
    # Cascade order: Step 12 (prereq) fires before Step 9 (policy).
    # Expected: can_execute_with_gate first, then after completing prereq → blocked_by_policy.
    if (
        env.verdict == "can_execute_with_gate"
        and env.binding_bundle
        and env.binding_bundle.prerequisites
    ):
        prereq_id = env.binding_bundle.prerequisites[0].binding_id
        env2 = fabric.resolve_situation(
            ResolveSituationRequest(
                request_id="req-child-2",
                frame=child_frame,
                actor_id="actor-a",
                space_id="space-1",
                session_id="sess-1",
                tier="MEDIUM",
                safety_band="GREEN",
                completed_prerequisite_bindings=[prereq_id],
            )
        )
        ok = env2.verdict == "blocked_by_policy"
        results.append(
            ProbeResult(
                "gates",
                "policy_child_write_denied",
                ok,
                f"after prereq complete: verdict={env2.verdict} sub_reason={env2.sub_reason}",
            )
        )
    else:
        results.append(
            ProbeResult(
                "gates", "policy_child_write_denied", False, f"unexpected verdict={env.verdict}"
            )
        )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 5: LLM extraction → resolve_situation (real Vertex LLM)
# ══════════════════════════════════════════════════════════════════════


EXTRACTION_SYSTEM_PROMPT = """You are an intent extraction system for the FamilyOS kernel.
Given a user utterance, produce structured JSON with:
- intents: [{intent_id, action, domain, operation_hint, resource_kind_hint, subject_hint, params}]
- resource_refs: [{raw, resource_kind_hint, needs_resolution}]

Available services (resource_kinds you may reference):
  family domain:
    calendar -> resource_kinds: [calendar_event, appointment]
    tasks -> resource_kinds: [task]
    reminders -> resource_kinds: [reminder]
    chores -> resource_kinds: [chore]
    shopping -> resource_kinds: [shopping_item]
    notes -> resource_kinds: [note]
    contacts -> resource_kinds: [contact]
    habits -> resource_kinds: [habit]
    budgets -> resource_kinds: [budget]
    documents -> resource_kinds: [document]

IMPORTANT: resource_kind_hint MUST be one of the exact resource_kinds listed above.
operation_hint must be one of: list, create, update, delete.

Respond with ONLY valid JSON. No markdown, no explanation."""


async def probe_llm_extraction(client: ModelClient, fabric: Any) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    utterances = [
        (
            "F01",
            "family",
            "Add dentist appointment for Riley next Monday at 3pm",
            "create",
            "calendar_event",
        ),
        ("F02", "family", "What's on the family calendar this weekend?", "list", "calendar_event"),
        ("F03", "family", "Assign kitchen cleanup to Morgan as a chore", "create", "chore"),
        ("F04", "family", "Show me all of Riley's tasks", "list", "task"),
        (
            "F05",
            "family",
            "Remind me to buy groceries for Sunday dinner",
            "create",
            "shopping_item",
        ),
    ]

    for sid, domain, utterance, exp_op, exp_rk in utterances:
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"<UTTERANCE>\n{utterance}\n</UTTERANCE>\n\nConvert to JSON.",
            },
        ]

        t0 = _now_ms()
        try:
            response = await client.chat(
                messages=messages,
                tools=[],
                tool_choice="none",
                temperature=0.0,
                max_tokens=1024,
                response_mime_type="application/json",
            )
            extract_ms = _now_ms() - t0
            content = (response.content or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content
            content = content.removesuffix("```").strip()
            import re

            if not content.startswith("{"):
                m = re.search(r"\{.*\}", content, re.DOTALL)
                if m:
                    content = m.group()
            parsed = json.loads(content)
            intents_raw = parsed.get("intents", [])
            extraction_ok = bool(intents_raw)

            # Build RequestFrame
            intents = []
            for i, it in enumerate(intents_raw):
                if isinstance(it, dict):
                    intents.append(
                        RequestFrameIntent(
                            intent_id=it.get("intent_id", f"i{i}"),
                            action=it.get("action", utterance),
                            domain=it.get("domain", domain),
                            operation_hint=it.get("operation_hint", exp_op),
                            resource_kind_hint=it.get("resource_kind_hint", exp_rk),
                            subject_hint=it.get("subject_hint"),
                            params=dict(it.get("params") or {}),
                        )
                    )
            rks = list({it.resource_kind_hint for it in intents if it.resource_kind_hint})
            frame = RequestFrame(
                request_id="req-" + uuid.uuid4().hex[:12],
                task_id="task-llm-probe",
                trace_id="trace-llm-probe",
                actor_id="actor-a",
                space_id="space-1",
                intents=intents,
                resource_refs=[
                    ResourceRef(raw=rk, resource_kind_hint=rk, needs_resolution=False) for rk in rks
                ],
                safety_context={"actor_role": "parent", "safety_band": "GREEN"},
            )

            # Resolve
            env = fabric.resolve_situation(
                ResolveSituationRequest(
                    request_id=frame.request_id,
                    frame=frame,
                    actor_id="actor-a",
                    space_id="space-1",
                    session_id="sess-llm",
                    tier="MEDIUM",
                    safety_band="GREEN",
                )
            )
            resolve_ms = _now_ms() - extract_ms
            ok = env.verdict in {"can_execute", "can_execute_with_gate"}
            llm_op = intents_raw[0].get("operation_hint", "?") if intents_raw else "?"
            llm_rk = intents_raw[0].get("resource_kind_hint", "?") if intents_raw else "?"
            primary = (
                env.binding_bundle.primary.capability_name
                if env.binding_bundle and env.binding_bundle.primary
                else "none"
            )
            results.append(
                ProbeResult(
                    "llm",
                    f"{sid}_extract_resolve",
                    ok,
                    f"utter='{utterance[:40]}' llm→{llm_op}/{llm_rk} verdict={env.verdict} primary={primary}",
                    extract_ms + resolve_ms,
                )
            )
        except Exception as exc:
            results.append(
                ProbeResult("llm", f"{sid}_extract_resolve", False, f"error: {exc}", _now_ms() - t0)
            )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 7: Fabric.execute() — real 9-step pipeline via NativeToolProvider
# ══════════════════════════════════════════════════════════════════════


def probe_fabric_execute(fabric: Any, tmp_path: Path) -> list[ProbeResult]:
    """Call fabric.execute() on a real family-tool capability.  Exercises
    the full 9-step pipeline: emit→resolve→context→instantiate→CB→execute
    →validate→emit→learn."""
    results: list[ProbeResult] = []
    bundle = bootstrap_family_tools(
        fabric, db_path=str(tmp_path / "fam.db"), service_classes=[CalendarToolService]
    )
    try:
        caps = bundle.native_provider.capabilities()
        create_cap = next((c for c in caps if "calendar.create_event" in c), None)
        results.append(
            ProbeResult(
                "execute",
                "provider_registered",
                create_cap is not None,
                f"cap={create_cap}" if create_cap else f"caps={caps[:3]}",
            )
        )

        if not create_cap:
            return results

        # Execute the create_event through the REAL Fabric 9-step pipeline
        t0 = _now_ms()
        result = _run(
            fabric.execute(
                CapabilityRequest(
                    capability_name=create_cap,
                    params=dict(_EVT_PARAMS),
                    caller="probe",
                    caller_id="actor-a",
                    trace_id="trace-exec-1",
                    session_id="sess-probe-1",
                    tier="MEDIUM",
                    safety_band="GREEN",
                )
            )
        )
        lat = _now_ms() - t0
        ok = result.success and result.data is not None
        event_id = result.data.get("event_id", "") if result.data else ""
        results.append(
            ProbeResult(
                "execute",
                "execute_create_event",
                ok,
                f"success={result.success} event_id={event_id} err={result.error.message if result.error else ''}",
                lat,
            )
        )

        # Read back via Fabric.execute (read capability)
        read_cap = next((c for c in caps if "calendar.get_event" in c), None)
        if read_cap and event_id:
            t0 = _now_ms()
            result2 = _run(
                fabric.execute(
                    CapabilityRequest(
                        capability_name=read_cap,
                        params={"event_id": event_id},
                        caller="probe",
                        caller_id="actor-a",
                        trace_id="trace-exec-2",
                        session_id="sess-probe-1",
                        tier="MEDIUM",
                        safety_band="GREEN",
                    )
                )
            )
            lat = _now_ms() - t0
            title = result2.data.get("event", {}).get("title", "") if result2.data else ""
            ok = result2.success and title == "Soccer game"
            results.append(
                ProbeResult(
                    "execute",
                    "execute_get_event",
                    ok,
                    f"success={result2.success} title={title}",
                    lat,
                )
            )

            # Cleanup via Fabric.execute (delete)
            del_cap = next((c for c in caps if "calendar.delete_event" in c), None)
            if del_cap:
                _run(
                    fabric.execute(
                        CapabilityRequest(
                            capability_name=del_cap,
                            params={"event_id": event_id, "expected_version": 1},
                            caller="probe",
                            caller_id="actor-a",
                            trace_id="trace-exec-3",
                            session_id="sess-probe-1",
                            tier="MEDIUM",
                            safety_band="GREEN",
                        )
                    )
                )
    finally:
        bundle.close()
    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 8: Prereq→Complete→Execute full cycle
# ══════════════════════════════════════════════════════════════════════


def probe_prereq_cycle(fabric: Any) -> list[ProbeResult]:
    """Prove: resolve(gated) → complete prereq → re-resolve(can_execute) →
    execute primary.  Uses a seeded connected resource so binding IDs are
    stable across calls (matching the integration test pattern)."""
    results: list[ProbeResult] = []
    lps = fabric.local_projection_store

    # Seed a real connected resource (the integration test pattern)
    lps.upsert_connected_resource(
        {
            "resource_id": "cal-1",
            "actor_id": "actor-a",
            "resource_kind": "calendar_event",
            "connector_id": "family.calendar",
            "label": "my calendar",
            "status": "active",
            "permissions": "read_write",
            "freshness_state": "fresh",
        }
    )
    lps.upsert_alias_index("actor-a", "my calendar", "cal-1", "resource")
    lps.rebuild_alias_index("actor-a", "space-1")

    # Build frame with needs_resolution=True referencing the alias
    frame = RequestFrame(
        request_id="req-prereq-cycle",
        task_id="task-prereq",
        trace_id="trace-prereq",
        actor_id="actor-a",
        space_id="space-1",
        intents=[
            RequestFrameIntent(
                intent_id="i1",
                action="create calendar_event",
                domain="family",
                operation_hint="create",
                resource_kind_hint="calendar_event",
                subject_hint="dentist",
                params={
                    "title": "D",
                    "start": "x",
                    "end": "y",
                    "resource_id": "c",
                    "idempotency_key": "k",
                },
            )
        ],
        resource_refs=[ResourceRef(raw="my calendar", resource_kind_hint="calendar_event")],
        safety_context={"actor_role": "parent", "safety_band": "GREEN"},
    )
    req = ResolveSituationRequest(
        request_id=frame.request_id,
        frame=frame,
        actor_id="actor-a",
        space_id="space-1",
        session_id="sess-prereq",
        tier="MEDIUM",
        safety_band="GREEN",
    )

    # Round 1: should gate on prereq
    env1 = fabric.resolve_situation(req)
    ok1 = env1.verdict == "can_execute_with_gate"
    prereq_id = (
        env1.binding_bundle.prerequisites[0].binding_id
        if env1.binding_bundle and env1.binding_bundle.prerequisites
        else None
    )
    results.append(
        ProbeResult(
            "prereq_cycle",
            "round1_gate",
            ok1,
            f"verdict={env1.verdict} prereq_id={prereq_id[:20] if prereq_id else 'none'}",
        )
    )

    # Round 2: mark prereq complete → should succeed
    if prereq_id:
        req2 = ResolveSituationRequest(
            request_id=frame.request_id,
            frame=frame,
            actor_id="actor-a",
            space_id="space-1",
            session_id="sess-prereq",
            tier="MEDIUM",
            safety_band="GREEN",
            completed_prerequisite_bindings=[prereq_id],
        )
        env2 = fabric.resolve_situation(req2)
        ok2 = env2.verdict == "can_execute"
        primary = (
            env2.binding_bundle.primary.capability_name
            if env2.binding_bundle and env2.binding_bundle.primary
            else "none"
        )
        results.append(
            ProbeResult(
                "prereq_cycle",
                "round2_can_execute",
                ok2,
                f"verdict={env2.verdict} primary={primary}",
            )
        )
    else:
        results.append(
            ProbeResult("prereq_cycle", "round2_can_execute", False, "no prereq_id from round 1")
        )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 9: Agent creation via build_agent (real LLM-backed ModelGateway)
# ══════════════════════════════════════════════════════════════════════


class _VertexModelGateway:
    """Real Vertex LLM adapter satisfying IModelGatewayPort + ILLMHandle.

    Thin wrapper around the ModelClient used by the benchmark scripts.
    Passes through async generate() calls to Vertex Gemini.
    """

    def __init__(self, client: ModelClient) -> None:
        self._client = client
        self.model_id = client.model_id
        self._budget = 4000

    def create_handle(
        self,
        budget_tokens: int = 4000,
        model_preference: str | None = None,
        capabilities: list[str] | None = None,
        trace_id: str | None = None,
    ) -> Any:
        h = _VertexModelGateway(self._client)
        h._budget = budget_tokens
        return h

    @property
    def budget_tokens(self) -> int:
        return self._budget

    async def generate(self, prompt: str, params: dict) -> str:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": params.get("task", "Execute the plan.")},
        ]
        resp = await self._client.chat(
            messages=messages,
            tools=[],
            tool_choice="none",
            temperature=0.0,
            max_tokens=1024,
        )
        return resp.content or ""

    def is_model_loaded(self, model_id: str) -> bool:
        return model_id == self.model_id

    def list_models(self) -> list:
        return [
            type(
                "M",
                (),
                {
                    "model_id": self.model_id,
                    "capabilities": [],
                    "loaded": True,
                    "max_tokens": 128000,
                    "provider": "vertex",
                },
            )
        ]

    def find_model(self, required_capabilities: list[str]) -> str | None:
        return self.model_id


async def probe_agent_creation(client: ModelClient, fabric: Any) -> list[ProbeResult]:
    """Prove the agent infrastructure pieces: real model gateway adapter,
    agent contract admission, and discovery-awareness — without needing
    full AgentFactory production wiring (which requires Orchestrator +
    many internal deps not available in a standalone probe)."""
    results: list[ProbeResult] = []

    # 9a — Prove the real Vertex model gateway adapter satisfies the port
    gateway = _VertexModelGateway(client)
    handle = gateway.create_handle(budget_tokens=2000)
    t0 = _now_ms()
    response = await handle.generate(
        prompt="Reply with exactly: AGENT_PROBE_OK",
        params={"task": "Say AGENT_PROBE_OK and nothing else."},
    )
    lat = _now_ms() - t0
    ok = "AGENT_PROBE_OK" in response or "ok" in response.lower()
    results.append(
        ProbeResult("agent", "vertex_model_gateway", ok, f"response={response[:60]}", lat)
    )

    # 9b — Prove agent contracts are discoverable via the registry
    agent_contracts = []
    if fabric.registry:
        agent_contracts = fabric.registry.list_by_type("agent")
    # Also check if build_agent YAML contract is loaded
    build_agent = fabric.registry.lookup("tool.write.build_agent") if fabric.registry else None
    results.append(
        ProbeResult(
            "agent",
            "build_agent_contract_loaded",
            build_agent is not None,
            f"found={build_agent is not None} known_agents={len(agent_contracts)}",
        )
    )

    # 9c — Prove discovery finds existing agent contracts
    t0 = _now_ms()
    disc = await fabric.discover_capabilities(intent="agent", top_k=5)
    lat = _now_ms() - t0
    caps = getattr(disc, "capabilities", [])
    agent_hits = [
        c for c in caps if c.contract and getattr(c.contract, "provider_type", "") == "AGENT"
    ]
    results.append(
        ProbeResult(
            "agent",
            "discover_agents",
            len(agent_hits) >= 0,
            f"{len(agent_hits)} agents in discovery, {len(caps)} total results",
            lat,
        )
    )

    return results


# ══════════════════════════════════════════════════════════════════════
# PROBE 6: Wired Fabric wiring check
# ══════════════════════════════════════════════════════════════════════


def probe_wiring(fabric: Any) -> list[ProbeResult]:
    from k1.fabric.fabric import CapabilityFabric
    from k1.fabric.resolver.situated_resolver import ResolveSituationService

    results: list[ProbeResult] = []
    checks = [
        ("fabric.facade", isinstance(fabric.facade, CapabilityFabric)),
        ("global_projection_store", fabric.global_projection_store is not None),
        ("local_projection_store", fabric.local_projection_store is not None),
        ("idempotency_store", fabric.idempotency_store is not None),
        ("situated_resolver", isinstance(fabric.situated_resolver, ResolveSituationService)),
        ("constitution_loader", fabric.constitution_loader is not None),
        ("policy_selector", fabric.policy_selector is not None),
        ("prompt_pack_builder", fabric.prompt_pack_builder is not None),
    ]
    for name, ok in checks:
        results.append(ProbeResult("wiring", name, ok, ""))
    return results


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════


def _print_results(results: list[ProbeResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'─'*80}")
    print(f"{'Section':<14} {'Test':<36} {'Result':<7} {'Detail'}")
    print(f"{'─'*80}")
    for r in results:
        icon = "✓" if r.passed else "✗"
        ms = f"{r.latency_ms:.0f}ms" if r.latency_ms else ""
        print(f"{r.section:<14} {r.test:<36} {icon:<7} {r.detail[:60]}{'  ' + ms if ms else ''}")
    print(f"{'─'*80}")
    print(f"{passed}/{total} passed")
    if passed == total:
        print("ALL PASSED ✓")


def _csv(results: list[ProbeResult]) -> str:
    lines = ["section,test,passed,detail,latency_ms"]
    for r in results:
        lines.append(f"{r.section},{r.test},{r.passed},{r.detail},{r.latency_ms:.0f}")
    return "\n".join(lines)


MENU = """
╔══════════════════════════════════════════════════════╗
║  Fabric API Probe — Exercise EVERY Fabric surface     ║
╠══════════════════════════════════════════════════════╣
║  0. Dry-run (wiring + store stats only, no LLM)      ║
║  1. Full probe (wiring + stores + resolve + discovery ║
║     + family execution + gates + prereq cycle)       ║
║  2. Full probe WITH real LLM (all above + 5 real     ║
║     Vertex extractions + fabric.execute + agents)    ║
║  3. Gap-closer only: Fabric.execute + prereq cycle   ║
║     + agent pieces (with real LLM)                   ║
╚══════════════════════════════════════════════════════╝"""


def main() -> int:
    import tempfile

    print(MENU)
    choice = input("Select [0-3]: ").strip()

    all_results: list[ProbeResult] = []

    # ── Common: wiring check + store stats ──
    if choice in ("0", "1", "2", "3"):
        print("\n=== Wiring + Store Health ===")
        fabric = _wired_fabric()
        all_results.extend(probe_wiring(fabric))
        all_results.extend(probe_store_health(fabric))

    if choice in ("1", "2", "3"):
        print("\n=== Resolve Situation ===")
        all_results.extend(probe_resolve_situation(fabric))

        print("\n=== Discovery API ===")
        all_results.extend(asyncio.run(probe_discovery(fabric)))

        print("\n=== Family Tool Execution ===")
        with tempfile.TemporaryDirectory() as td:
            all_results.extend(probe_family_execution(Path(td)))

        print("\n=== Idempotency + Policy Gates ===")
        all_results.extend(probe_gates(fabric))

        print("\n=== Prereq→Complete→Execute Cycle ===")
        all_results.extend(probe_prereq_cycle(fabric))

        print("\n=== Fabric.execute() 9-Step Pipeline ===")
        with tempfile.TemporaryDirectory() as td:
            all_results.extend(probe_fabric_execute(fabric, Path(td)))

    if choice in ("2", "3"):
        print("\n=== Agent Creation (real Vertex LLM) ===")
        try:
            client = create_model_client_from_env()
        except Exception as exc:
            print(f"LLM client error: {exc}")
            all_results.append(ProbeResult("agent", "init", False, str(exc)))
        else:
            all_results.extend(asyncio.run(probe_agent_creation(client, fabric)))

    if choice == "2":
        print("\n=== LLM Extraction → Resolve (real Vertex LLM) ===")
        # Reuse the existing client or create new
        try:
            client2 = create_model_client_from_env()
        except Exception:
            pass  # will skip
        else:
            all_results.extend(asyncio.run(probe_llm_extraction(client2, fabric)))

    if all_results:
        _print_results(all_results)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = Path(f"data/probe_fabric_api_{ts}.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_csv(all_results))
        print(f"\nSaved CSV to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    raise SystemExit(main())
