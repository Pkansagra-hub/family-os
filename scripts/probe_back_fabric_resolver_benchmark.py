"""Back Resolver Benchmark — on the REAL ``k1.fabric`` (no POC, no mocks).

Proves the full Tier-2 spine — Extraction → Resolution → Verdict — runs through
the **real wired Fabric** (the exact object graph the kernel assembles on its
per-session P3 path), not the POC sandbox.

PIPELINE
  Phase 1 (Extract):  real Vertex LLM turns an utterance + full K1 context into
                      a structured frame (intents / person_refs / resource_refs).
  Phase 2 (Build):    that extraction → the REAL
                      ``k1.fabric.resolver.request_frame.RequestFrame``.
  Phase 3 (Resolve):  ``Fabric.resolve_situation(request)`` — the real 13-step
                      cascade over the real ``GlobalProjectionStore`` /
                      ``LocalProjectionStore`` / ``IdempotencyStore``, with the
                      real 50-connector domain catalog admitted via the real
                      ``ManifestAdmissionService``.
  Phase 4 (Score):    extraction pass, verdict pass, and 3-layer tool accuracy
                      (candidate / commit / execution) — by domain.

NO benchmark-side keyword heuristics.  The POC resolver benchmark carried big
``_UNIVERSAL_CONCEPT_ALIASES`` / ``_seed_global_graph`` tables to bridge LLM
vocabulary to capabilities.  Here the **real catalog builder + admission** seed
the graph ontology (concept aliases, operation aliases, typed index) — exactly
as they do at kernel boot.  The benchmark adds nothing.

VOCABULARY ALIGNMENT
  The LLM context's ``AVAILABLE SERVICES`` block is regenerated from the REAL
  ``k1.fabric`` catalog (``DOMAIN_SERVICES``), so the model is told the exact
  ``resource_kinds`` the real catalog admits and extracts matching vocabulary.
  The family domain is the fully-aligned reference (its scenario ground truth,
  the LLM context, and the real catalog all share one vocabulary).

Usage:
  $env:LLM_PROVIDER="vertex"
  $env:GOOGLE_CLOUD_PROJECT="<project>"
  $env:GOOGLE_CLOUD_LOCATION="global"
  python scripts/probe_back_fabric_resolver_benchmark.py
  # Mode 1: dry-run (real catalog stats). Mode 2: full pipeline (LLM + real Fabric).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows consoles default to cp1252; the report uses box-drawing + ✓/✗ glyphs.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8")
        except Exception:
            pass

# ── REAL k1.fabric wiring (the kernel's own factory + port adapters) ───
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
    TimeWindowHint,
)
from k1.fabric.resolver.situated_resolver import ResolveSituationRequest
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.idempotency_store import IdempotencyStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ── Real Vertex LLM client (extraction only — the model wrapper) ───────
from poc.back_tool_contract_v2.model_client import (
    ModelClient,
    create_model_client_from_env,
)

# ── Scenarios / contexts / extraction prompt (reused verbatim) ─────────
from scripts.probe_back_llm_frame_benchmark_v3 import (
    ALL_DOMAIN_CONTEXTS,
    FRAME_EXTRACTION_SYSTEM_PROMPT,
    SCENARIOS,
    DomainContext,
    FrameScenario,
    build_context_block,
)

# ═══════════════════════════════════════════════════════════════════
# VERDICTS
# ═══════════════════════════════════════════════════════════════════

VERDICT_PASS = {"can_execute", "can_execute_with_gate"}

_READ_OPS = {"list", "read", "search", "get", "view", "check", "find"}


# ═══════════════════════════════════════════════════════════════════
# REAL-CATALOG CONTEXT — regenerate the LLM's service block from k1.fabric
# ═══════════════════════════════════════════════════════════════════


def _real_services_for_domain(domain_id: str) -> list[dict[str, Any]]:
    """Build the LLM ``services`` block from the REAL ``k1.fabric`` catalog.

    The model is told the exact ``resource_kinds`` the real catalog admits, so
    its extracted ``resource_kind_hint`` matches what ``resolve_situation`` can
    actually bind.  No POC vocabulary, no bridging aliases.
    """
    services: list[dict[str, Any]] = []
    for sd in DOMAIN_SERVICES[domain_id]:
        resource_kinds = [sd.resource] + [rk for rk in sd.resource_kinds if rk != sd.resource]
        services.append(
            {
                "service_id": sd.id,
                "label": sd.label,
                "description": sd.desc,
                "resource_kinds": resource_kinds,
            }
        )
    return services


def _context_with_real_services(ctx: DomainContext) -> DomainContext:
    """Clone a v3 ``DomainContext`` with its service block sourced from the real
    catalog.  Roster / self-model / grounding / beliefs / task-state are kept."""
    return replace(ctx, services=_real_services_for_domain(ctx.domain_id))


def _actor_space(ctx: DomainContext) -> tuple[str, str]:
    actor_id = ctx.self_model.get("actor_id", "actor_001")
    space_id = (
        ctx.roster.get("space_id")
        or ctx.roster.get("org_id")
        or ctx.roster.get("farm_id")
        or ctx.roster.get("practice_id")
        or "space_001"
    )
    return actor_id, space_id


# ═══════════════════════════════════════════════════════════════════
# GROUND TRUTH — expected capability names, derived from the REAL catalog
# ═══════════════════════════════════════════════════════════════════


def _build_resource_kind_index() -> dict[str, dict[str, tuple[str, str, str | None]]]:
    """Map (domain → resource_kind → (service_id, read_op, write_op)) from the
    real catalog.  Sole source of truth for ground-truth tool names."""
    index: dict[str, dict[str, tuple[str, str, str | None]]] = {}
    for domain_id, services in DOMAIN_SERVICES.items():
        dmap: dict[str, tuple[str, str, str | None]] = {}
        for sd in services:
            for rk in [sd.resource] + list(sd.resource_kinds):
                dmap.setdefault(rk, (sd.id, sd.read_op, sd.write_op))
        index[domain_id] = dmap
    return index


_RK_INDEX = _build_resource_kind_index()


def ground_truth_tools(scenario: FrameScenario) -> list[str]:
    """Expected capability names for a scenario, from the real catalog.

    ``tool.{read|execute}.{domain}.{service_id}.{action}`` — read actions use the
    service's ``read_op``; create→``write_op``; update/delete/send map directly.
    """
    domain = scenario.domain_id
    dmap = _RK_INDEX.get(domain, {})
    tools: list[str] = []
    for i, op in enumerate(scenario.expected_operations):
        rk = (
            scenario.expected_resource_kinds[i]
            if i < len(scenario.expected_resource_kinds)
            else None
        )
        if not rk or rk not in dmap:
            continue
        service_id, read_op, write_op = dmap[rk]
        if op in _READ_OPS:
            mode, action = "read", read_op
        elif op == "create":
            mode, action = "execute", (write_op or "create")
        elif op in ("update", "delete", "send"):
            mode, action = "execute", op
        else:
            mode, action = "execute", op
        tools.append(f"tool.{mode}.{domain}.{service_id}.{action}")
    return tools


# ═══════════════════════════════════════════════════════════════════
# REAL FABRIC — wire once, seed every domain's connected resources
# ═══════════════════════════════════════════════════════════════════


def _ports() -> dict[str, Any]:
    """The six kernel-grade infra port adapters ``FabricFactory`` expects.

    ``resolve_situation`` never touches bus / bridge / model / prompt / state —
    it reads only the stores — so these adapters do not taint the resolution
    path; it is end-to-end real.
    """
    return dict(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
    )


def build_real_fabric() -> Any:
    """Construct the real wired Fabric: real stores, real admitted catalog,
    real per-domain connected resources — exactly the kernel's P3 graph."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    lps = LocalProjectionStore(":memory:")
    lps.open()
    idem = IdempotencyStore(":memory:")
    idem.open()

    # Admit the full 50-connector catalog via the real admission service.
    admission = ManifestAdmissionService(gps)
    for corpus in build_all_corpora().values():
        admission.admit_all(corpus)

    # Seed one connected resource per service for every domain (real kinds).
    for domain_id, services in DOMAIN_SERVICES.items():
        ctx = ALL_DOMAIN_CONTEXTS.get(domain_id)
        if ctx is None:
            continue
        actor_id, _space = _actor_space(ctx)
        for sd in services:
            connector_id = f"{domain_id}.{sd.id}"
            lps.upsert_connected_resource(
                {
                    "resource_id": f"res_{domain_id}_{sd.id}",
                    "actor_id": actor_id,
                    "resource_kind": sd.resource,
                    "connector_id": connector_id,
                    "label": sd.label,
                    "status": "active",
                    "permissions": "read_write",
                    "freshness_state": "fresh",
                }
            )
        lps.rebuild_alias_index(actor_id, _space)

    return FabricFactory.create_with_ports(
        **_ports(),
        global_projection_store=gps,
        local_projection_store=lps,
        idempotency_store=idem,
    )


# ═══════════════════════════════════════════════════════════════════
# PHASE 2 — BUILD THE REAL RequestFrame FROM LLM EXTRACTION
# ═══════════════════════════════════════════════════════════════════


def build_request_frame(
    scenario: FrameScenario,
    ctx: DomainContext,
    extraction: dict[str, Any],
) -> RequestFrame:
    """Convert LLM extraction JSON → the REAL ``RequestFrame`` (no heuristics)."""
    actor_id, space_id = _actor_space(ctx)

    intents_raw = extraction.get("intents") or []
    intents: list[RequestFrameIntent] = []
    for i, intent in enumerate(intents_raw):
        if not isinstance(intent, dict):
            continue
        intents.append(
            RequestFrameIntent(
                intent_id=f"intent_{i:03d}",
                action=intent.get("action", scenario.utterance),
                domain=intent.get("domain") or scenario.domain_id,
                operation_hint=intent.get("operation_hint", ""),
                resource_kind_hint=intent.get("resource_kind_hint"),
                subject_hint=intent.get("subject_hint"),
                params=dict(intent.get("params") or {}),
            )
        )

    # Resource refs: one per distinct resource_kind_hint.  needs_resolution=False
    # → the resolver builds a direct candidate and the binder resolves against
    # the real catalog (the true test of "does the real Fabric resolve this").
    resource_refs: list[ResourceRef] = []
    seen: set[str] = set()
    for it in intents:
        rk = it.resource_kind_hint
        if rk and rk not in seen:
            seen.add(rk)
            resource_refs.append(ResourceRef(raw=rk, resource_kind_hint=rk, needs_resolution=False))

    time_hint = None
    raw_tw = extraction.get("time_window_hint")
    if isinstance(raw_tw, dict) and raw_tw.get("raw_phrase"):
        time_hint = TimeWindowHint(
            raw_phrase=raw_tw.get("raw_phrase", ""),
            confidence=raw_tw.get("confidence", "medium"),
        )

    return RequestFrame(
        request_id="req-" + uuid.uuid4().hex[:12],
        task_id="task-" + uuid.uuid4().hex[:8],
        trace_id="trace-" + uuid.uuid4().hex[:16],
        actor_id=actor_id,
        space_id=space_id,
        intents=intents,
        person_refs=[],
        resource_refs=resource_refs,
        time_window_hint=time_hint,
        safety_context={
            "actor_role": ctx.self_model.get("role", "parent"),
            "safety_band": "GREEN",
            "session_id": "session_bench_001",
        },
        target_tier="tier2",
        resolution_mode="execution",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def build_resolve_request(frame: RequestFrame) -> ResolveSituationRequest:
    """Wrap the frame in the REAL ``ResolveSituationRequest``."""
    return ResolveSituationRequest(
        request_id=frame.request_id,
        frame=frame,
        actor_id=frame.actor_id,
        space_id=frame.space_id,
        session_id="session_bench_001",
        tier="MEDIUM",
        safety_band="GREEN",
        disclosure_phase="connector_summary",
        prompt_budget_tokens=8000,
    )


# ═══════════════════════════════════════════════════════════════════
# RESULT TYPE
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ScenarioResult:
    scenario_id: str
    domain_id: str
    utterance: str
    extraction_passed: bool
    verdict: str
    sub_reason: str | None
    verdict_passed: bool
    tools_needed: list[str]
    tools_found_all: list[str]
    tools_found_primary: list[str]
    tools_committed: list[str]
    candidate_recall: float
    commit_accuracy: float
    execution_safety: float
    allowed_actions: list[str]
    diag: list[str]
    extraction_raw: dict[str, Any]
    latency_extract_ms: float
    latency_resolve_ms: float


# ═══════════════════════════════════════════════════════════════════
# PHASE 1 + 3 — EXTRACT (LLM) then RESOLVE (real Fabric)
# ═══════════════════════════════════════════════════════════════════


async def run_scenario(
    client: ModelClient,
    scenario: FrameScenario,
    ctx: DomainContext,
    context_block: str,
    fabric: Any,
) -> ScenarioResult:
    system_prompt = FRAME_EXTRACTION_SYSTEM_PROMPT + "\n\n" + context_block
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"<CURRENT_UTTERANCE>\n{scenario.utterance}\n</CURRENT_UTTERANCE>\n\n"
                "Convert this utterance to structured JSON as specified."
            ),
        },
    ]

    # ── Phase 1: Extract (real Vertex LLM) ──
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
        extract_ms = (time.perf_counter() - start) * 1000
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
            extraction_ok = bool(parsed.get("intents"))
        except json.JSONDecodeError:
            parsed = {"error": "json_parse_failed", "raw": content[:200]}
            extraction_ok = False
    except Exception as exc:
        extract_ms = (time.perf_counter() - start) * 1000
        parsed = {"error": str(exc)}
        extraction_ok = False

    # ── Phase 2: Build the real RequestFrame ──
    frame = build_request_frame(scenario, ctx, parsed)
    request = build_resolve_request(frame)

    # ── Phase 3: Resolve through the REAL Fabric ──
    needed = ground_truth_tools(scenario)
    needed_set = set(needed)
    resolve_ms = 0.0
    verdict = "resolver_error"
    sub_reason: str | None = None
    verdict_ok = False
    all_caps: list[str] = []
    primary_caps: list[str] = []
    committed: list[str] = []
    allowed_actions: list[str] = []
    diag: list[str] = []

    resolve_start = time.perf_counter()
    try:
        envelope = fabric.resolve_situation(request)
        resolve_ms = (time.perf_counter() - resolve_start) * 1000
        verdict = envelope.verdict
        sub_reason = envelope.sub_reason
        verdict_ok = verdict in VERDICT_PASS
        allowed_actions = list(envelope.allowed_next_actions)
        committed = list(envelope.allowed_capability_names)

        bundle = envelope.binding_bundle
        if bundle is not None:
            for b in bundle.all_bindings:
                all_caps.append(b.capability_name)
                if b.role == "primary":
                    primary_caps.append(b.capability_name)

        # Diagnostics on non-pass verdicts.
        if not verdict_ok:
            if sub_reason:
                diag.append(f"{verdict}: {sub_reason}")
            universe = envelope.candidate_universe
            for u in getattr(universe, "unresolved", []) or []:
                diag.append(f"unresolved[{u.reason}]: {u.raw}")
            if bundle is not None:
                for role in bundle.unbound_roles:
                    diag.append(f"unbound[{role.reason}]: {getattr(role, 'resource_kind', '?')}")
    except Exception as exc:  # pragma: no cover - benchmark resilience
        resolve_ms = (time.perf_counter() - resolve_start) * 1000
        verdict = f"resolver_error: {type(exc).__name__}"
        diag.append(str(exc))

    all_set, primary_set, committed_set = set(all_caps), set(primary_caps), set(committed)
    n = len(needed_set) or 1
    return ScenarioResult(
        scenario_id=scenario.id,
        domain_id=scenario.domain_id,
        utterance=scenario.utterance,
        extraction_passed=extraction_ok,
        verdict=verdict,
        sub_reason=sub_reason,
        verdict_passed=verdict_ok,
        tools_needed=needed,
        tools_found_all=sorted(all_set),
        tools_found_primary=sorted(primary_set),
        tools_committed=sorted(committed_set),
        candidate_recall=round(len(needed_set & all_set) / n, 3),
        commit_accuracy=round(len(needed_set & primary_set) / n, 3),
        execution_safety=round(len(needed_set & committed_set) / n, 3),
        allowed_actions=allowed_actions,
        diag=diag,
        extraction_raw=parsed,
        latency_extract_ms=round(extract_ms, 1),
        latency_resolve_ms=round(resolve_ms, 1),
    )


# ═══════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════


def _short(cap: str) -> str:
    parts = cap.split(".")
    if len(parts) >= 5 and parts[0] == "tool":
        return f"{parts[3]}.{parts[4]}"
    return cap


async def run_benchmark(client: ModelClient) -> dict[str, Any]:
    provider = os.environ.get("LLM_PROVIDER", "unknown")
    print(f"Provider: {provider} | Model: {client.model_id}")
    print("Target  : REAL k1.fabric (FabricFactory + real stores + real catalog)")
    print("Pipeline: Extract (LLM) → RequestFrame → Fabric.resolve_situation → Verdict")

    # Build the real wired Fabric ONCE (kernel P3 graph).
    fabric = build_real_fabric()
    gps = fabric.global_projection_store
    print(
        f"Catalog : {len(gps.list_connectors())} connectors, "
        f"{gps.count_capabilities()} capabilities admitted (real ManifestAdmissionService)"
    )

    # LLM context per domain — service block sourced from the REAL catalog.
    contexts: dict[str, tuple[DomainContext, str]] = {}
    for domain_id, ctx in ALL_DOMAIN_CONTEXTS.items():
        real_ctx = _context_with_real_services(ctx)
        contexts[domain_id] = (real_ctx, build_context_block(real_ctx))
    print(f"Scenarios: {len(SCENARIOS)} across {len(ALL_DOMAIN_CONTEXTS)} domains\n")

    results: list[ScenarioResult] = []
    for i, scenario in enumerate(SCENARIOS):
        real_ctx, ctx_block = contexts[scenario.domain_id]
        print(
            f"[{i+1:02d}/{len(SCENARIOS)}] {scenario.id} [{scenario.domain_id}]: "
            f"{scenario.utterance[:58]}"
        )
        result = await run_scenario(client, scenario, real_ctx, ctx_block, fabric)
        results.append(result)

        e = "✓" if result.extraction_passed else "✗"
        v = "✓" if result.verdict_passed else "✗"
        needed_short = [_short(t) for t in result.tools_needed]
        got_short = [_short(t) for t in result.tools_found_all]
        print(
            f"         Extract {e} | Verdict {result.verdict:<26} {v}"
            f" | {result.latency_extract_ms:.0f}ms+{result.latency_resolve_ms:.0f}ms"
        )
        layer = (
            f"cand={result.candidate_recall:.2f} commit={result.commit_accuracy:.2f} "
            f"exec={result.execution_safety:.2f}"
        )
        if needed_short:
            layer += f" | need=[{','.join(needed_short)}]"
        if got_short:
            layer += f" got=[{','.join(got_short[:4])}]" + (
                f"+{len(got_short)-4}" if len(got_short) > 4 else ""
            )
        print(f"         Tools   {layer}")
        for d in result.diag[:2]:
            print(f"         Diag    {d}")

    return _aggregate(results, provider, client.model_id, gps)


def _aggregate(
    results: list[ScenarioResult],
    provider: str,
    model_id: str,
    gps: Any,
) -> dict[str, Any]:
    total = len(results)
    extract_ok = sum(1 for r in results if r.extraction_passed)
    verdict_ok = sum(1 for r in results if r.verdict_passed)

    verdict_counts: dict[str, int] = {}
    for r in results:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

    domain_rows: dict[str, dict[str, Any]] = {}
    for domain_id in ALL_DOMAIN_CONTEXTS:
        dr = [r for r in results if r.domain_id == domain_id]
        if not dr:
            continue
        # Tool-accuracy is only meaningful where the scenario's expected
        # resource_kinds map onto the REAL catalog.  Scenarios whose POC-era
        # vocabulary predates the real catalog have no ground truth — the
        # Fabric still resolved them, but they are 'unmapped', not failures.
        scored = [r for r in dr if r.tools_needed]
        domain_rows[domain_id] = {
            "total": len(dr),
            "extract_ok": sum(1 for r in dr if r.extraction_passed),
            "verdict_ok": sum(1 for r in dr if r.verdict_passed),
            "scored": len(scored),
            "unmapped": len(dr) - len(scored),
            "cand": (
                round(statistics.mean(r.candidate_recall for r in scored), 3) if scored else None
            ),
            "commit": (
                round(statistics.mean(r.commit_accuracy for r in scored), 3) if scored else None
            ),
            "exec": (
                round(statistics.mean(r.execution_safety for r in scored), 3) if scored else None
            ),
        }

    avg_extract = statistics.mean(r.latency_extract_ms for r in results)
    avg_resolve = statistics.mean(r.latency_resolve_ms for r in results)

    # Tool-accuracy aggregate over MAPPABLE scenarios only (ground truth exists).
    scored_all = [r for r in results if r.tools_needed]
    n_scored = len(scored_all)
    n_unmapped = total - n_scored
    agg_cand = (
        round(statistics.mean(r.candidate_recall for r in scored_all), 3) if scored_all else 0.0
    )
    agg_commit = (
        round(statistics.mean(r.commit_accuracy for r in scored_all), 3) if scored_all else 0.0
    )
    agg_exec = (
        round(statistics.mean(r.execution_safety for r in scored_all), 3) if scored_all else 0.0
    )

    print(f"\n{'='*72}")
    print("REAL-FABRIC RESOLVER BENCHMARK — Extract → resolve_situation → Verdict")
    print(f"{'='*72}")
    print(f"Provider: {provider} | Model: {model_id}")
    print(f"Catalog : {len(gps.list_connectors())} connectors, {gps.count_capabilities()} caps")
    print(f"Extraction OK: {extract_ok}/{total} ({round(extract_ok/total*100)}%)")
    print(f"Verdict PASS : {verdict_ok}/{total} ({round(verdict_ok/total*100)}%)")
    print(f"Avg latency  : {avg_extract:.0f}ms extract + {avg_resolve:.0f}ms resolve")
    print(
        f"Tool layers  : cand={agg_cand:.2f} commit={agg_commit:.2f} exec={agg_exec:.2f} "
        f"(over {n_scored} mappable; {n_unmapped} unmapped — POC-era scenario vocab)\n"
    )

    print("Verdict distribution:")
    for verdict, count in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        print(f"  {verdict:<32} {count:>3} {'█'*min(count,40)}")
    print()

    def _fmt(v: float | None) -> str:
        return "  n/a" if v is None else f"{v:>5.2f}"

    print("By domain (family is the fully-aligned reference; n/a = scenario vocab")
    print("predates the real catalog — Fabric still resolved, nothing to score against):")
    print(
        f"  {'Domain':<13}{'Extract':>8}{'Verdict':>8}{'map':>6}{'cand':>7}{'commit':>8}{'exec':>7}"
    )
    print(f"  {'─'*57}")
    for domain_id in ["family", "enterprise", "government", "agriculture", "healthcare"]:
        row = domain_rows.get(domain_id)
        if not row:
            continue
        print(
            f"  {domain_id:<13}"
            f"{row['extract_ok']:>4}/{row['total']:<3}"
            f"{row['verdict_ok']:>4}/{row['total']:<3}"
            f"{row['scored']:>4}/{row['total']:<1}"
            f"{_fmt(row['cand'])}{_fmt(row['commit'])}{_fmt(row['exec'])}"
        )

    return {
        "provider": provider,
        "model": model_id,
        "target": "k1.fabric (real)",
        "connectors": len(gps.list_connectors()),
        "capabilities": gps.count_capabilities(),
        "total": total,
        "extract_ok": extract_ok,
        "verdict_ok": verdict_ok,
        "extract_pct": round(extract_ok / total * 100),
        "verdict_pct": round(verdict_ok / total * 100),
        "verdict_counts": verdict_counts,
        "domain_scores": domain_rows,
        "tool_accuracy_scored": {
            "mappable_scenarios": n_scored,
            "unmapped_scenarios": n_unmapped,
            "avg_candidate_recall": agg_cand,
            "avg_commit_accuracy": agg_commit,
            "avg_execution_safety": agg_exec,
        },
        "avg_extract_ms": round(avg_extract, 1),
        "avg_resolve_ms": round(avg_resolve, 1),
        "results": [
            {
                "id": r.scenario_id,
                "domain": r.domain_id,
                "utterance": r.utterance,
                "extraction_passed": r.extraction_passed,
                "verdict": r.verdict,
                "sub_reason": r.sub_reason,
                "verdict_passed": r.verdict_passed,
                "tools_needed": r.tools_needed,
                "tools_found_all": r.tools_found_all,
                "tools_found_primary": r.tools_found_primary,
                "tools_committed": r.tools_committed,
                "candidate_recall": r.candidate_recall,
                "commit_accuracy": r.commit_accuracy,
                "execution_safety": r.execution_safety,
                "allowed_actions": r.allowed_actions,
                "diagnostics": r.diag,
                "latency_extract_ms": r.latency_extract_ms,
                "latency_resolve_ms": r.latency_resolve_ms,
            }
            for r in results
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════════╗
║   Back Resolver Benchmark — on the REAL k1.fabric         ║
║   Extract → RequestFrame → resolve_situation → Verdict    ║
╠══════════════════════════════════════════════════════════╣
║  1. Dry-run (real catalog stats, no LLM, no resolve)     ║
║  2. Run full pipeline (real Vertex LLM + real Fabric)    ║
║  0. Exit                                                 ║
╚══════════════════════════════════════════════════════════╝"""


def main() -> int:
    print(MENU)
    choice = input("Select [1-2, 0]: ").strip()

    if choice == "1":
        corpora = build_all_corpora()
        total_connectors = sum(len(c) for c in corpora.values())
        total_caps = sum(sum(len(m.capabilities) for m in corpus) for corpus in corpora.values())
        print("DRY RUN — Real-Fabric Resolver Benchmark")
        print(f"Domains: {len(corpora)} | Connectors: {total_connectors} | Caps: {total_caps}")
        print(f"Scenarios: {len(SCENARIOS)}")
        for domain_id, corpus in corpora.items():
            caps = sum(len(m.capabilities) for m in corpus)
            print(f"  {domain_id:<12}: {len(corpus)} connectors, {caps} capabilities")
        print("\nPipeline: Extract → RequestFrame → Fabric.resolve_situation → Verdict")
        print("Family domain is the fully-aligned reference vocabulary.")
        return 0

    if choice == "2":
        try:
            client = create_model_client_from_env()
        except Exception as exc:
            print(f"\nERROR: {exc}")
            print("Set $env:LLM_PROVIDER, $env:GOOGLE_CLOUD_PROJECT, $env:GOOGLE_CLOUD_LOCATION")
            return 1

        provider = os.environ.get("LLM_PROVIDER", "unknown")
        print(f"\nProvider: {provider} | Model: {client.model_id}")
        print("Running 50 scenarios through the REAL Fabric...\n")

        result = asyncio.run(run_benchmark(client))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_slug = client.model_id.replace("/", "_").replace("-", "_")
        out_path = Path(
            f"data/llm_frame_bench/results_fabric_resolver_{provider}_{model_slug}_{ts}.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to {out_path}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
